"""The whole pipeline, end to end, with a scripted AI and a throwaway SQLite 'clinical' database."""

import pytest
from sqlalchemy import create_engine, text

from app.graph.runner import run_chat
from tests.fakes import ScriptedLLM, make_deps

ROUTE_SQL = '{"kind": "sql", "databases": ["clinical"], "reason": "count of patients"}'


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT)"))
        for i in range(111):
            conn.execute(text("INSERT INTO patients VALUES (:i, 'A', 'B', '1990-01-01', 'F')"), {"i": f"p{i}"})
    return engine


def _run(llm, engine, role="clinician", patient_id=None):
    deps = make_deps(llm, engines={"clinical": engine})
    return run_chat(deps, "How many patients are there?", role, patient_id, "session-1")


def test_happy_path(engine):
    llm = ScriptedLLM(ROUTE_SQL, "```sql\nSELECT count(*) AS n FROM patients\n```",
                      "There are 111 patients. Source: clinical_db.patients")
    result = _run(llm, engine)
    assert result.kind == "answer"
    assert "111" in result.answer
    assert len(result.sql) == 1
    assert result.sql[0].query == "SELECT count(*) AS n FROM patients"  # what the AI wrote
    assert result.sql[0].error is None
    assert result.sources == ["clinical_db.patients"]
    assert result.table.rows == [[111]]
    assert {"route", "inject_schema", "generate_sql", "validate", "execute", "synthesize", "verify_numbers"} <= set(result.timings)


def test_retry_then_success(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT cnt FROM patients", "SELECT count(*) AS n FROM patients",
                      "There are 111 patients.")
    result = _run(llm, engine)
    assert result.kind == "answer"
    assert len(result.sql) == 2
    assert "cnt" in result.sql[0].error and result.sql[1].error is None


def test_gives_up_after_three_failures(engine):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT a FROM patients", "SELECT b FROM patients", "SELECT c FROM patients")
    result = _run(llm, engine)
    assert result.kind == "error" and len(result.sql) == 3


def test_refusal_path(engine):
    llm = ScriptedLLM('{"kind": "refuse", "databases": [], "reason": "other patients"}')
    result = _run(llm, engine, role="patient", patient_id="p1")
    assert result.kind == "refusal" and "your own records" in result.answer
    assert result.sql == []


def test_out_of_scope_path(engine):
    llm = ScriptedLLM('{"kind": "out_of_scope", "databases": [], "reason": "weather"}')
    result = _run(llm, engine)
    assert result.kind == "out_of_scope"


def test_billing_route_falls_back_to_clinical_for_now(engine):
    llm = ScriptedLLM('{"kind": "sql", "databases": ["billing"], "reason": "claims"}',
                      "SELECT count(*) AS n FROM patients", "There are 111 patients.")
    result = _run(llm, engine)
    assert result.kind == "answer" and result.sql[0].db == "clinical"


def test_llm_failure_returns_error_kind(engine):
    result = _run(ScriptedLLM(RuntimeError("429 Too Many Requests")), engine)
    assert result.kind == "error"
    assert "rate-limited" in result.answer
