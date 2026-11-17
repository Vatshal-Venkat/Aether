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
    # final review: a table aliased with another table's name hid the SSN column
    "SELECT encounters.ssn AS x FROM patients AS encounters JOIN encounters AS e ON e.patient = encounters.id",
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


# --- MySQL billing_db: no built-in RLS, so the row-filter rewrite must contain every trick ------
from app.graph.nodes.row_filter import row_filter  # noqa: E402
from app.graph.state import Link, QueryResult, StepResult  # noqa: E402

# (attack SQL, table whose OWN-row count bounds any number in the result — None if no numbers)
MYSQL_ATTACKS = [
    ("SELECT count(*) AS n FROM claims", "claims"),
    ("SELECT count(*) AS n FROM claims WHERE 1=1 OR patientid IS NOT NULL", "claims"),
    ("SELECT DISTINCT patientid FROM claims UNION SELECT patientid FROM claims_transactions", None),
    ("SELECT DISTINCT c.patientid FROM claims c JOIN claims_transactions t ON t.claimid = c.id", None),
    ("WITH claims AS (SELECT * FROM billing_db.claims) SELECT DISTINCT patientid FROM claims", None),
    ("SELECT DISTINCT patient FROM payer_transitions", None),
    ("SELECT (SELECT count(*) FROM claims) AS n", "claims"),
    ("SELECT count(*) AS n FROM billing_db.claims_transactions", "claims_transactions"),
    ("SELECT DISTINCT patientid FROM claims WHERE patientid IN (SELECT patientid FROM claims_transactions)", None),
    ("SELECT count(DISTINCT patient) AS n FROM payer_transitions", "patients"),
    ("SELECT sum(amount_covered) AS s FROM payers", None),   # population total: must be rejected
    # final review: payers aliased as "claims" hid its population totals
    ("SELECT claims.name, claims.amount_covered FROM payers AS claims CROSS JOIN claims AS c2", None),
]


@pytest.fixture(scope="module")
def billing_setup():
    requires_db("billing")
    requires_db("clinical")
    s = get_settings()
    engines = {"clinical": create_engine(s.clinical_url()), "billing": create_engine(s.billing_url())}
    glossary = load_glossary()
    deps = Deps(settings=s, llm=ScriptedLLM(), catalog=build_catalog(engines, glossary),
                glossary=glossary, engines=engines)
    admin = create_engine(s.billing_url(admin=True))
    with admin.connect() as conn:
        pid, other = conn.execute(text("SELECT DISTINCT patientid FROM claims ORDER BY patientid LIMIT 2")).scalars()
        all_ids = set(conn.execute(text("SELECT DISTINCT patientid FROM claims")).scalars())
        own = {t: conn.execute(text(f"SELECT count(*) FROM {t} WHERE {c} = :p"), {"p": pid}).scalar()
               for t, c in (("claims", "patientid"), ("claims_transactions", "patientid"),
                            ("payer_transitions", "patient"))}
    own["patients"] = 1
    admin.dispose()
    yield deps, pid, other, all_ids, own
    for e in engines.values():
        e.dispose()


def _run_billing(deps, pid, sql, **extra):
    state = {"db": "billing", "role": "patient", "patient_id": pid, "step": extra.pop("step", 0),
             "attempts": [{"step": extra.get("step", 0), "db": "billing", "sql": sql, "executed": None, "error": None}],
             **extra}
    state.update(validate(state, deps))
    if state["final_sql"] is None:
        return None
    state.update(row_filter(state, deps))
    assert state["final_sql"] is not None, state["attempts"][-1]["error"]
    out = execute(state, deps)
    assert out["result"] is not None, out["attempts"][-1]["error"]
    return out["result"]


def _assert_only_own(result, pid, all_ids, own_max=0):
    flat = [v for row in result.rows for v in row]
    leaked = {v for v in flat if isinstance(v, str) and v in all_ids and v != pid}
    assert not leaked, f"other patients visible: {leaked}"
    assert all(not isinstance(v, (int, float)) or v <= own_max for v in flat), f"count too big: {flat}"


@pytest.mark.parametrize("sql, count_table", MYSQL_ATTACKS)
def test_mysql_attack_never_reveals_other_patients(billing_setup, sql, count_table):
    deps, pid, _, all_ids, own = billing_setup
    result = _run_billing(deps, pid, sql)
    if "amount_covered" in sql:
        assert result is None, "population column must be rejected in patient mode"
        return
    if result is not None:
        _assert_only_own(result, pid, all_ids, own[count_table] if count_table else 0)


def test_cross_db_link_values_still_patient_filtered(billing_setup):
    # Step 1 "found" two patient ids (own + someone else's): step 2 must still show only own rows.
    deps, pid, other, all_ids, _ = billing_setup
    link = Link(from_table="patients", from_column="id", to_table="claims", to_column="patientid")
    step1 = QueryResult(columns=["id"], rows=[[pid], [other]], total_rows=2, truncated=False)
    result = _run_billing(deps, pid, "SELECT patientid, count(*) AS n FROM claims GROUP BY patientid",
                          step=1, link=link,
                          step_results=[StepResult(db="clinical", sql="-", result=step1, sources=[])])
    assert {r[0] for r in result.rows} == {pid}
