"""First pipeline steps: route the question, pick relevant tables, write SQL."""

import time

from app.graph.nodes.generate_sql import extract_sql, generate_sql
from app.graph.nodes.inject_schema import inject_schema
from app.graph.nodes.route import route
from app.graph.state import RouteDecision
from app.graph.timing import timed
from tests.fakes import ScriptedLLM, make_deps

CLINICIAN = {"role": "clinician", "patient_id": None}
PATIENT = {"role": "patient", "patient_id": "p-123"}


# --- route -------------------------------------------------------------------------------
def test_route_parses_decision():
    llm = ScriptedLLM('{"kind": "sql", "databases": ["clinical"], "reason": "lab results"}')
    out = route({"question": "How many patients?", **CLINICIAN}, make_deps(llm))
    assert out["route"] == RouteDecision(kind="sql", databases=["clinical"], reason="lab results")
    assert "route" in out["timings"]


def test_route_prompt_mentions_patient_rules_in_patient_mode():
    llm = ScriptedLLM('{"kind": "refuse", "databases": [], "reason": "asks about others"}')
    route({"question": "How many patients have diabetes?", **PATIENT}, make_deps(llm))
    prompt = llm.prompt_text().lower()
    assert "patient mode" in prompt and "refuse" in prompt


# --- inject_schema -------------------------------------------------------------------------
def _schema_for(question: str) -> str:
    state = {"question": question, **CLINICIAN, "route": RouteDecision(kind="sql", databases=["clinical"], reason="")}
    return inject_schema(state, make_deps(ScriptedLLM()))["schema_text"]


def test_inject_schema_always_includes_patients():
    assert "TABLE patients" in _schema_for("What allergies are recorded?")


def test_inject_schema_picks_observations_for_hba1c():
    text = _schema_for("What is my latest HbA1c?")
    assert "TABLE observations" in text
    assert "Hemoglobin A1c" in text  # the glossary hint travels with the schema


def test_inject_schema_picks_medications():
    text = _schema_for("Which medications am I taking?")
    assert "TABLE medications" in text
    assert "TABLE allergies" not in text


# --- generate_sql --------------------------------------------------------------------------
def test_extract_sql_variants():
    assert extract_sql("Here you go:\n```sql\nSELECT 1;\n```\nThanks") == "SELECT 1"
    assert extract_sql("SELECT a FROM b;  ") == "SELECT a FROM b"
    assert extract_sql("Here is the query: SELECT a FROM b") == "SELECT a FROM b"
    assert extract_sql("```\nWITH x AS (SELECT 1) SELECT * FROM x\n```") == "WITH x AS (SELECT 1) SELECT * FROM x"


def test_generate_sql_appends_attempt():
    llm = ScriptedLLM("```sql\nSELECT count(*) FROM patients\n```")
    state = {"question": "How many patients?", **CLINICIAN, "schema_text": "TABLE patients", "attempts": []}
    out = generate_sql(state, make_deps(llm))
    assert out["attempts"] == [{"step": 0, "db": "clinical", "sql": "SELECT count(*) FROM patients",
                                "executed": None, "error": None}]
    assert "PostgreSQL" in llm.prompt_text()


def test_generate_sql_retry_includes_previous_error():
    llm = ScriptedLLM("SELECT count(*) FROM patients")
    failed = [{"sql": "SELECT cnt FROM patients", "error": 'column "cnt" does not exist'}]
    state = {"question": "How many?", **CLINICIAN, "schema_text": "TABLE patients", "attempts": failed}
    out = generate_sql(state, make_deps(llm))
    assert 'column "cnt" does not exist' in llm.prompt_text()
    assert len(out["attempts"]) == 2


def test_generate_sql_patient_mode_says_rows_are_prefiltered():
    llm = ScriptedLLM("SELECT description FROM medications")
    generate_sql({"question": "my meds?", **PATIENT, "schema_text": "TABLE medications", "attempts": []}, make_deps(llm))
    assert "automatically limited" in llm.prompt_text()


# --- timing --------------------------------------------------------------------------------
def test_timed_records_seconds():
    @timed("slow_step")
    def node(state, deps):
        time.sleep(0.01)
        return {"x": 1}

    out = node({}, None)
    assert out["x"] == 1 and out["timings"]["slow_step"] >= 0.01
