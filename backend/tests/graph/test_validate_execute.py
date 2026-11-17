"""validate -> execute -> retry decision."""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.graph.edges import after_execute, after_validate
from app.graph.nodes.execute import execute
from app.graph.nodes.simple_replies import fail
from app.graph.nodes.validate import validate
from app.graph.state import QueryResult
from tests.conftest import requires_db
from tests.fakes import ScriptedLLM, make_deps

CLINICIAN = {"role": "clinician", "patient_id": None}


def _attempt(sql, error=None):
    return {"sql": sql, "error": error}


# --- edges (pure) ------------------------------------------------------------------------
def test_error_retries_until_limit():
    state = {"attempts": [_attempt("x", "boom")]}
    assert after_validate(state, max_attempts=3) == "generate_sql"
    assert after_execute(state, max_attempts=3) == "generate_sql"


def test_error_after_limit_fails():
    state = {"attempts": [_attempt("x", "e1"), _attempt("y", "e2"), _attempt("z", "e3")]}
    assert after_validate(state, max_attempts=3) == "fail"
    assert after_execute(state, max_attempts=3) == "fail"


def test_success_moves_on():
    assert after_validate({"attempts": [_attempt("SELECT 1")]}, max_attempts=3) == "execute"


def test_empty_result_does_not_retry():
    state = {"attempts": [_attempt("SELECT 1")], "result": QueryResult(columns=["a"], rows=[], total_rows=0, truncated=False)}
    assert after_execute(state, max_attempts=3) == "synthesize"


# --- validate (pure) -----------------------------------------------------------------------
def test_validate_failure_records_error():
    state = {"db": "clinical", "attempts": [_attempt("DELETE FROM patients")], **CLINICIAN}
    out = validate(state, make_deps(ScriptedLLM()))
    assert out["attempts"][-1]["error"] and out["final_sql"] is None


def test_validate_success_sets_final_sql_with_limit():
    state = {"db": "clinical", "attempts": [_attempt("SELECT first FROM patients")], **CLINICIAN}
    out = validate(state, make_deps(ScriptedLLM()))
    assert out["attempts"][-1]["error"] is None
    assert "LIMIT 1001" in out["final_sql"]  # cap + 1, so truncation can be detected


def test_fail_node_message():
    out = fail({"attempts": []}, make_deps(ScriptedLLM()))
    assert out["kind"] == "error" and "3 tries" in out["answer"]


# --- execute on a throwaway SQLite database (runs anywhere) ----------------------------------
@pytest.fixture
def sqlite_deps():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, ssn TEXT, birthdate DATE, spend NUMERIC)"))
        for i in range(8):
            conn.execute(text("INSERT INTO patients VALUES (:i, :f, '999-00-0000', '1990-01-02', 12.5)"),
                         {"i": f"p{i}", "f": f"Name{i}"})
    return make_deps(ScriptedLLM(), engines={"clinical": engine}, rows_stored_cap=5)


def _exec(deps, sql):
    return execute({"db": "clinical", "final_sql": sql, "attempts": [_attempt(sql)], **CLINICIAN}, deps)


def test_execute_returns_rows_and_sources(sqlite_deps):
    out = _exec(sqlite_deps, "SELECT first FROM patients WHERE id = 'p1'")
    assert out["result"].rows == [["Name1"]] and out["result"].columns == ["first"]
    assert out["sources"] == ["clinical_db.patients"]


def test_execute_strips_pii_columns(sqlite_deps):
    out = _exec(sqlite_deps, "SELECT id, ssn FROM patients WHERE id = 'p0'")
    assert out["result"].columns == ["id"] and out["result"].rows == [["p0"]]


def test_execute_truncates(sqlite_deps):
    out = _exec(sqlite_deps, "SELECT id FROM patients")
    assert len(out["result"].rows) == 5 and out["result"].truncated is True


def test_truncation_detected_through_validate_and_execute(sqlite_deps):
    # Review I1: the LIMIT added by validate must leave room to notice "there were more rows".
    state = {"db": "clinical", "attempts": [_attempt("SELECT id FROM patients")], **CLINICIAN}
    state.update(validate(state, sqlite_deps))
    out = execute(state, sqlite_deps)
    assert len(out["result"].rows) == 5
    assert out["result"].truncated is True


def test_execute_db_error_recorded(sqlite_deps):
    out = _exec(sqlite_deps, "SELECT no_such_column FROM patients")
    assert out["result"] is None
    assert "no_such_column" in out["attempts"][-1]["error"]


def test_execute_handles_percent_signs(sqlite_deps):
    out = _exec(sqlite_deps, "SELECT first FROM patients WHERE first LIKE 'Name%' AND id = 'p2'")
    assert out["result"].rows == [["Name2"]]


def test_json_safe_values():
    from app.graph.nodes.execute import json_safe

    assert json_safe(Decimal("1.50")) == 1.5
    assert json_safe(dt.date(2020, 1, 2)) == "2020-01-02"
    assert json_safe(dt.datetime(2020, 1, 2, 3, 4)) == "2020-01-02T03:04:00"


# --- execute against the real PostgreSQL (patient privacy) -----------------------------------
@pytest.mark.db
def test_execute_patient_mode_filters():
    requires_db("clinical")
    engine = create_engine(get_settings().clinical_url())
    admin = create_engine(get_settings().clinical_url(admin=True))
    with admin.connect() as conn:
        pid, n = conn.execute(text(
            "SELECT patient, count(*) FROM encounters GROUP BY patient ORDER BY patient LIMIT 1")).one()
    deps = make_deps(ScriptedLLM(), engines={"clinical": engine})
    out = execute({"db": "clinical", "final_sql": "SELECT count(*) AS n FROM encounters",
                   "attempts": [_attempt("x")], "role": "patient", "patient_id": pid}, deps)
    assert out["result"].rows == [[n]]
