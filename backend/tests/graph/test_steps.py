"""The per-step query loop: schema, SQL writing, row filter and execution for one plan step."""

import pytest
from sqlalchemy import create_engine, text

from app.graph.edges import after_execute, after_validate
from app.graph.nodes.execute import execute
from app.graph.nodes.generate_sql import generate_sql
from app.graph.nodes.inject_schema import inject_schema
from app.graph.nodes.row_filter import row_filter
from app.graph.state import Link, PlanStep, QueryResult, RouteDecision, StepResult
from tests.fakes import ScriptedLLM, make_deps

Q = "Which doctor has seen the most patients? Give the doctor's name."
LINK = Link(from_table="encounters", from_column="provider", to_table="providers", to_column="id")
TWO_STEPS = [PlanStep(db="clinical", goal="count distinct patients per provider id"),
             PlanStep(db="billing", goal="names of those providers")]


@pytest.fixture
def engines():
    billing = create_engine("sqlite://")
    with billing.begin() as conn:
        conn.execute(text("CREATE TABLE claims (id TEXT, patientid TEXT, outstandingp REAL)"))
        conn.execute(text("INSERT INTO claims VALUES ('c1','p1',10), ('c2','p1',5), ('c3','p2',99)"))
        conn.execute(text("CREATE TABLE providers (id TEXT, name TEXT)"))
        conn.execute(text("INSERT INTO providers VALUES ('d1','Dr One'), ('d2','Dr Two'), ('d3','Dr Three')"))
    clinical = create_engine("sqlite://")
    with clinical.begin() as conn:
        conn.execute(text("CREATE TABLE encounters (id TEXT, patient TEXT, provider TEXT)"))
        conn.execute(text("INSERT INTO encounters VALUES ('e1','p1','d1'), ('e2','p2','d1'), ('e3','p1','d2')"))
    return {"clinical": clinical, "billing": billing}


def _state(step=0, role="clinician", pid=None, plan=None, link=LINK, **extra):
    plan = plan or TWO_STEPS
    return {"question": Q, "role": role, "patient_id": pid,
            "route": RouteDecision(kind="sql", databases=[s.db for s in plan]),
            "plan": plan, "link": link, "step": step, "db": plan[step].db,
            "step_results": [], "attempts": [], **extra}


def _step1_result(ids):
    rows = [[i, 1] for i in ids]
    return StepResult(db="clinical", sql="SELECT provider, n ...", sources=["clinical_db.encounters"],
                      result=QueryResult(columns=["provider", "n"], rows=rows, total_rows=len(rows), truncated=False))


# --- inject_schema -----------------------------------------------------------------------
def test_schema_uses_step_db_and_goal():
    out = inject_schema(_state(step=1), make_deps(ScriptedLLM()))
    assert "TABLE providers" in out["schema_text"]
    assert "TABLE patients" not in out["schema_text"] and "TABLE encounters" not in out["schema_text"]


def test_schema_forces_link_table_on_step0():
    plan = [PlanStep(db="clinical", goal="something vague"), TWO_STEPS[1]]
    out = inject_schema(_state(plan=plan), make_deps(ScriptedLLM()))
    assert "TABLE encounters" in out["schema_text"]


def test_patient_schema_hides_population_columns():
    plan = [PlanStep(db="billing", goal="my insurer payers name revenue")]
    deps = make_deps(ScriptedLLM())
    patient = inject_schema(_state(plan=plan, link=None, role="patient", pid="p1"), deps)["schema_text"]
    clinician = inject_schema(_state(plan=plan, link=None), deps)["schema_text"]
    lines = lambda text: {line.split()[0] for line in text.splitlines() if line.startswith("  ")}  # noqa: E731
    assert "TABLE payers" in patient and "revenue" not in lines(patient) and "phone" in lines(patient)
    assert "revenue" in lines(clinician)


# --- generate_sql ------------------------------------------------------------------------
def test_step1_notes_in_prompt():
    llm = ScriptedLLM("SELECT provider, count(*) AS n FROM encounters GROUP BY provider")
    out = generate_sql({**_state(), "schema_text": "TABLE encounters"}, make_deps(llm))
    prompt = llm.prompt_text()
    assert "Overall question: " + Q in prompt and "This step: count distinct patients per provider id" in prompt
    assert "Include the column encounters.provider in the output, unaliased" in prompt
    assert out["attempts"][-1] == {"step": 0, "db": "clinical", "sql": "SELECT provider, count(*) AS n FROM encounters GROUP BY provider",
                                   "executed": None, "error": None}
    assert "PostgreSQL" in prompt


def test_step2_notes_in_prompt():
    llm = ScriptedLLM("SELECT id, name FROM providers")
    state = {**_state(step=1, step_results=[_step1_result(["d1", "d2"])]), "schema_text": "TABLE providers"}
    out = generate_sql(state, make_deps(llm))
    prompt = llm.prompt_text()
    assert "keep only providers rows whose id is one of the 2 values found in step 1" in prompt
    assert "MySQL" in prompt and "no ILIKE" in prompt
    assert out["attempts"][-1]["step"] == 1 and out["attempts"][-1]["db"] == "billing"


def test_step2_after_a_ranking_is_a_plain_lookup():
    # Live (2026-11-19): "Which patient owes us the most? top 5" — step 1 summed the balances correctly; step 2
    # invented its own "amount_owed" (lifetime expenses minus coverage) and the answer ranked by THAT.
    llm = ScriptedLLM("SELECT id, name FROM providers")
    state = {**_state(step=1, step_results=[_step1_result(["d1", "d2"])]), "schema_text": "TABLE providers"}
    generate_sql(state, make_deps(llm))
    prompt = llm.prompt_text()
    assert "Step 1 already worked out: n" in prompt
    assert "Do not compute any amount, count or ranking" in prompt and "no ORDER BY or LIMIT" in prompt


def test_step2_after_ids_only_may_still_aggregate():
    llm = ScriptedLLM("SELECT sum(outstandingp) FROM claims")
    ids_only = StepResult(db="clinical", sql="SELECT provider ...", sources=["clinical_db.encounters"],
                          result=QueryResult(columns=["provider"], rows=[["d1"]], total_rows=1, truncated=False))
    generate_sql({**_state(step=1, step_results=[ids_only]), "schema_text": "x"}, make_deps(llm))
    assert "already worked out" not in llm.prompt_text()
    assert "for an overall total you may aggregate" in llm.prompt_text()


def test_previous_errors_shown_only_for_this_step():
    llm = ScriptedLLM("SELECT id, name FROM providers")
    old = [{"step": 0, "db": "clinical", "sql": "SELECT bad0", "executed": None, "error": "step0 boom"}]
    state = {**_state(step=1, step_results=[_step1_result(["d1"])], attempts=old), "schema_text": "x"}
    generate_sql(state, make_deps(llm))
    assert "step0 boom" not in llm.prompt_text()


# --- row_filter ---------------------------------------------------------------------------
def _attempt(sql, step=0, db="billing"):
    return {"step": step, "db": db, "sql": sql, "executed": None, "error": None}


def _run_filter_and_execute(state, engines):
    deps = make_deps(ScriptedLLM(), engines=engines)
    state.update(row_filter(state, deps))
    if state["attempts"][-1]["error"]:
        return state, None
    state.update(execute(state, deps))
    return state, state["result"]


def test_row_filter_patient_billing(engines):
    plan = [PlanStep(db="billing", goal="how much do I owe")]
    sql = "SELECT sum(outstandingp) AS owed FROM claims"
    state = _state(plan=plan, link=None, role="patient", pid="p1", attempts=[_attempt(sql)], final_sql=sql)
    state, result = _run_filter_and_execute(state, engines)
    assert "patientid = 'p1'" in state["attempts"][-1]["executed"]
    assert result.rows == [[15.0]]


def test_row_filter_clinician_billing_unchanged(engines):
    plan = [PlanStep(db="billing", goal="total owed")]
    sql = "SELECT sum(outstandingp) AS owed FROM claims"
    state = _state(plan=plan, link=None, attempts=[_attempt(sql)], final_sql=sql)
    state, result = _run_filter_and_execute(state, engines)
    assert state["attempts"][-1]["executed"] is None and result.rows == [[114.0]]


def test_row_filter_link_values(engines):
    sql = "SELECT id, name FROM providers ORDER BY id"
    state = _state(step=1, step_results=[_step1_result(["d1", "d2", "d1", None])],
                   attempts=[_attempt(sql, step=1)], final_sql=sql)
    state, result = _run_filter_and_execute(state, engines)
    assert "IN ('d1', 'd2')" in state["attempts"][-1]["executed"]
    assert result.rows == [["d1", "Dr One"], ["d2", "Dr Two"]]


def test_row_filter_missing_link_table_is_error(engines):
    sql = "SELECT sum(outstandingp) FROM claims"
    state = _state(step=1, step_results=[_step1_result(["d1"])], attempts=[_attempt(sql, step=1)], final_sql=sql)
    state, result = _run_filter_and_execute(state, engines)
    assert result is None and "Use the table providers" in state["attempts"][-1]["error"]


def test_row_filter_unsafe_value_is_error(engines):
    sql = "SELECT id, name FROM providers"
    state = _state(step=1, step_results=[_step1_result(["x' OR '1'='1"])], attempts=[_attempt(sql, step=1)], final_sql=sql)
    state, result = _run_filter_and_execute(state, engines)
    assert result is None and state["attempts"][-1]["error"]


# --- execute: the key column for step 2 must be there -------------------------------------
def test_missing_key_column_is_error(engines):
    sql = "SELECT count(*) AS n FROM encounters"
    state = _state(attempts=[_attempt(sql, db="clinical")], final_sql=sql)
    out = execute(state, make_deps(ScriptedLLM(), engines=engines))
    assert out["result"] is None and "Include the column provider" in out["attempts"][-1]["error"]


def test_key_column_present_ok(engines):
    sql = "SELECT provider, count(*) AS n FROM encounters GROUP BY provider"
    state = _state(attempts=[_attempt(sql, db="clinical")], final_sql=sql)
    out = execute(state, make_deps(ScriptedLLM(), engines=engines))
    assert out["result"].total_rows == 2


# --- tries are counted per step ------------------------------------------------------------
def test_retries_counted_per_step():
    attempts = [{**_attempt("a", 0), "error": "e"}, {**_attempt("b", 0), "error": "e"}, _attempt("c", 0),
                {**_attempt("d", 1), "error": "e"}]
    state = {"step": 1, "attempts": attempts}
    assert after_validate(state, max_attempts=3) == "generate_sql"
    assert after_execute(state, max_attempts=3) == "generate_sql"


def test_step2_notes_say_step1_conditions_already_applied():
    # Live test X2: the AI re-applied "diabetes" in billing with an invented diagnosis code -> nothing matched.
    llm = ScriptedLLM("SELECT id, name FROM providers")
    state = {**_state(step=1, step_results=[_step1_result(["d1"])]), "schema_text": "TABLE providers"}
    generate_sql(state, make_deps(llm))
    assert "already" in llm.prompt_text() and "do not repeat" in llm.prompt_text().lower()


# --- validate: a lookup step after a ranking ------------------------------------------------
# Accuracy report 2026-11-23 (XD06): told "this step is a plain lookup", the AI still re-computed the amount owed
# (16,946 from visit costs instead of step 1's 2,313.07) or selected step 1's column, which this database lacks.
# Code now rejects both, so the retry gets a clear reason.
def _lookup(sql):
    from app.graph.nodes.validate import validate
    state = _state(step=1, step_results=[_step1_result(["d1", "d2"])],
                   attempts=[{"step": 1, "db": "billing", "sql": sql, "executed": None, "error": None}])
    return validate(state, make_deps(ScriptedLLM()))


def test_lookup_step_may_not_compute_amounts():
    out = _lookup("SELECT id, name, COUNT(*) AS visits FROM providers GROUP BY id, name")
    assert out["final_sql"] is None and "only looks up" in out["attempts"][-1]["error"]


def test_lookup_step_may_not_use_step1_columns():
    out = _lookup("SELECT id, name, n FROM providers")
    assert out["final_sql"] is None and "n" in out["attempts"][-1]["error"]


def test_plain_lookup_passes():
    out = _lookup("SELECT id, name FROM providers")
    assert out["final_sql"] is not None and out["attempts"][-1]["error"] is None


# Accuracy report 2026-11-24 (XD02, XD07): balances came out as 779,415.28 and 131,652.91 instead of 211.38 and
# 2,313.07 — the AI summed claims_transactions.outstanding (a running balance repeated on every line item) although
# the glossary says not to. Code now rejects it and the retry is told which column to use.
def _single(sql):
    from app.graph.nodes.validate import validate
    plan = [PlanStep(db="billing", goal="balances")]
    state = _state(plan=plan, link=None, attempts=[{"step": 0, "db": "billing", "sql": sql, "executed": None, "error": None}])
    return validate(state, make_deps(ScriptedLLM()))


def test_summing_the_line_item_running_balance_is_rejected():
    out = _single("SELECT patientid, SUM(ct.outstanding) AS owed FROM claims_transactions ct GROUP BY patientid")
    assert out["final_sql"] is None and "claims.outstandingp" in out["attempts"][-1]["error"]


def test_summing_what_the_patient_still_owes_passes():
    out = _single("SELECT patientid, SUM(outstandingp) AS owed FROM claims GROUP BY patientid")
    assert out["final_sql"] is not None
