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
class _Library:  # the drug-label library, as far as the spelling check needs it
    def drug_names(self):
        return ["metformin er 500 mg", "lisinopril", "metoprolol succinate"]


def test_misspelled_medicine_asks_did_you_mean_before_anything_else():
    llm = ScriptedLLM('{"kind": "rag", "databases": [], "reason": "drug info", "drugs": ["metformin"]}')
    out = route({"question": "What are the side effects of metfromin?", **CLINICIAN}, make_deps(llm, store=_Library()))
    decision = out["route"]
    assert decision.kind == "clarify" and decision.clarify_question == "Did you mean metformin?"
    assert decision.options == ["Yes", "No"]
    assert decision.option_questions == {"Yes": "What are the side effects of metformin?", "No": ""}


def test_spelling_is_checked_on_what_the_person_typed():
    # A follow-up rewrite may already have "fixed" the spelling; the person still gets asked.
    llm = ScriptedLLM('{"kind": "hybrid", "databases": ["clinical"], "reason": "my meds"}')
    state = {"question": "Is my metformin safe with alcohol?", "original_question": "and my metfromin?", **PATIENT}
    out = route(state, make_deps(llm, store=_Library()))
    assert out["route"].kind == "clarify"
    assert out["route"].option_questions["Yes"] == "Is my metformin safe with alcohol?"


def test_spelling_check_only_for_drug_questions():
    llm = ScriptedLLM('{"kind": "sql", "databases": ["clinical"], "reason": "records"}')
    out = route({"question": "How many patients take metfromin?", **CLINICIAN}, make_deps(llm, store=_Library()))
    assert out["route"].kind == "sql"
    llm = ScriptedLLM('{"kind": "rag", "databases": [], "reason": "drug info"}')
    out = route({"question": "Side effects of metformin?", **CLINICIAN}, make_deps(llm, store=_Library()))
    assert out["route"].kind == "rag"


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
