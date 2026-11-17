"""End-to-end privacy regression: in patient mode, known attack queries must never reveal other
patients — run through the real validate + execute steps against the real PostgreSQL database."""

import pytest
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.db.catalog import build_catalog
from app.graph.deps import Deps
from app.graph.nodes.execute import execute
from app.graph.nodes.validate import validate
from app.semantic.glossary import load_glossary
from tests.conftest import requires_db
from tests.fakes import ScriptedLLM

pytestmark = pytest.mark.db

ATTACKS = [
    # review C1: identity switch via dynamic SQL, then count everyone
    "SELECT query_to_xml('select set_config(''app.role'',''clinician'',true)', true, false, '') AS a, "
    "(xpath('count(/table/row)', query_to_xml('select id from patients', true, false, '')))[1]::text AS n",
    "SELECT query_to_xml('select ssn from patients', true, false, '')",
    "SELECT id FROM patients WHERE set_config('app.role', 'clinician', true) IS NOT NULL",
    # review C2: CTE shadowing
    "WITH patients AS (SELECT ssn AS x FROM public.patients) SELECT x FROM patients",
    # plain attempts that the database itself must contain
    "SELECT count(*) AS n FROM patients WHERE 1=1 OR id IS NOT NULL",
    "SELECT count(DISTINCT patient) AS n FROM encounters",
]


@pytest.fixture(scope="module")
def deps_and_patient():
    requires_db("clinical")
    s = get_settings()
    engine = create_engine(s.clinical_url())
    glossary = load_glossary()
    deps = Deps(settings=s, llm=ScriptedLLM(), catalog=build_catalog({"clinical": engine}, glossary),
                glossary=glossary, engines={"clinical": engine})
    admin = create_engine(s.clinical_url(admin=True))
    with admin.connect() as conn:
        pid = conn.execute(text("SELECT id FROM patients ORDER BY id LIMIT 1")).scalar()
    admin.dispose()
    yield deps, pid
    engine.dispose()


@pytest.mark.parametrize("sql", ATTACKS)
def test_attack_never_reveals_other_patients(deps_and_patient, sql):
    deps, pid = deps_and_patient
    state = {"db": "clinical", "role": "patient", "patient_id": pid, "attempts": [{"sql": sql, "error": None}]}
    state.update(validate(state, deps))
    if state["final_sql"] is None:
        return  # rejected by the safety check: good
    out = execute(state, deps)
    assert out["result"] is not None, out["attempts"][-1]["error"]
    flat = [v for row in out["result"].rows for v in row]
    assert all(not isinstance(v, (int, float)) or v <= 1 for v in flat), f"saw more than one patient: {flat}"
    assert not any(isinstance(v, str) and "-" in v and len(v) == 11 and v.count("-") == 2 for v in flat), "SSN-like value leaked"
