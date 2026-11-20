"""Follow-up questions, clarifying questions, and the memory that makes them work."""

import json

import pytest
from sqlalchemy import create_engine, text

from app.graph.runner import run_chat, stream_chat
from app.memory.store import ConversationStore, Turn
from tests.fakes import ScriptedLLM, make_deps

ROUTE_SQL = '{"kind": "sql", "databases": ["clinical"], "reason": "count"}'


@pytest.fixture
def engine():
    e = create_engine("sqlite://")
    with e.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT)"))
        conn.execute(text("INSERT INTO patients VALUES ('p1','Ann1','Lee2','1990-01-01','F'), ('p2','Bob3','Ray4','1980-01-01','M')"))
    return e


@pytest.fixture
def memory(tmp_path):
    return ConversationStore(tmp_path / "m.sqlite")


def remember(memory, question, answer, kind="answer", session="s", role="clinician", patient=None):
    memory.add(Turn(session_id=session, role=role, patient_id=patient, question=question, standalone=question,
                    answer=answer, kind=kind))


def test_no_history_no_contextualize_call(engine, memory):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT count(*) AS n FROM patients", "There are 2 patients.")  # exactly 3 calls
    result = run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "How many patients?", "clinician", None, "s")
    assert result.kind == "answer" and result.standalone_question is None


def test_followup_is_rewritten_and_used_downstream(engine, memory):
    remember(memory, "How many patients are there?", "There are 2 patients.")
    llm = ScriptedLLM(json.dumps({"standalone": "How many female patients are there?"}), ROUTE_SQL,
                      "SELECT count(*) AS n FROM patients WHERE gender = 'F'", "There is 1 female patient.")
    result = run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "And how many of them are female?",
                      "clinician", None, "s")
    assert result.answer.startswith("There is 1") and result.table.rows == [[1]]
    assert result.standalone_question == "How many female patients are there?"
    rewrite_prompt = llm.prompt_text(0)
    assert "How many patients are there?" in rewrite_prompt and "There are 2 patients." in rewrite_prompt
    assert "How many female patients are there?" in llm.prompt_text(2)  # the SQL writer sees the standalone question


def test_clarification_result_with_options(engine, memory):
    clarify = {"kind": "clarify", "databases": [], "reason": "ambiguous",
               "clarify_question": "Revenue of what — a hospital or an insurance company?", "options": ["Hospitals", "Insurers"]}
    result = run_chat(make_deps(ScriptedLLM(json.dumps(clarify)), engines={"clinical": engine}, memory=memory),
                      "What's the revenue?", "clinician", None, "s")
    assert result.kind == "clarification" and result.route == "clarify"
    assert result.answer == "Revenue of what — a hospital or an insurance company?"
    assert result.options == ["Hospitals", "Insurers"]
    assert memory.turns("s")[-1].kind == "clarification"


class _Library:
    def drug_names(self):
        return ["metformin er 500 mg", "lisinopril"]


def test_misspelled_medicine_end_to_end(engine, memory):
    # One AI call (the router) and then a code-made "did you mean?" — no SQL, no label search, no answer drafting.
    llm = ScriptedLLM('{"kind": "rag", "databases": [], "reason": "drug info"}')
    deps = make_deps(llm, engines={"clinical": engine}, memory=memory, store=_Library())
    result = run_chat(deps, "What are the side effects of metfromin?", "clinician", None, "s")
    assert result.kind == "clarification" and result.answer == "Did you mean metformin?"
    assert result.options == ["Yes", "No"]
    assert result.option_questions == {"Yes": "What are the side effects of metformin?", "No": ""}
    assert result.sql == [] and result.documents == []


def test_clarification_then_choice(engine, memory):
    remember(memory, "What's the revenue?", "Revenue of what — a hospital or an insurance company?", kind="clarification")
    llm = ScriptedLLM(json.dumps({"standalone": "Which insurance company has the highest revenue?"}),
                      '{"kind": "out_of_scope", "databases": [], "reason": "test stops here"}')
    result = run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "Insurers", "clinician", None, "s")
    assert "Revenue of what" in llm.prompt_text(0) and "Insurers" in llm.prompt_text(0)
    assert result.standalone_question == "Which insurance company has the highest revenue?"
    assert "highest revenue" in llm.prompt_text(1)  # the router saw the full question


def test_followup_standalone_still_privacy_checked(engine, memory):
    remember(memory, "What medications am I taking?", "You take lisinopril.", role="patient", patient="p1")
    llm = ScriptedLLM(json.dumps({"standalone": "What medications is Bob3 Ray4 taking?"}))  # no route call scripted
    deps = make_deps(llm, engines={"clinical": engine}, memory=memory)
    deps.patient_names = {"p1": "Ann1 Lee2", "p2": "Bob3 Ray4"}
    result = run_chat(deps, "and what about Bob3?", "patient", "p1", "s")
    assert result.kind == "refusal"


def test_history_of_another_patient_is_not_used(engine, memory):
    remember(memory, "What medications am I taking?", "You take insulin.", role="patient", patient="p2")
    llm = ScriptedLLM(ROUTE_SQL, "SELECT count(*) AS n FROM patients", "1 record.")  # no rewrite call: no history for p1
    run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "And the dose?", "patient", "p1", "s")
    assert all("insulin" not in llm.prompt_text(i) for i in range(len(llm.calls)))


def test_every_turn_is_saved(engine, memory):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT count(*) AS n FROM patients", "There are 2 patients.")
    run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "How many patients?", "clinician", None, "s")
    saved = memory.turns("s")
    assert len(saved) == 1 and saved[0].question == "How many patients?" and saved[0].kind == "answer"


def test_stream_reports_recalling_only_with_history(engine, memory):
    llm = ScriptedLLM(ROUTE_SQL, "SELECT count(*) AS n FROM patients", "There are 2 patients.")
    events = list(stream_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "How many?", "clinician", None, "s"))
    assert "contextualize" not in [e["data"].get("step") for e in events if e["event"] == "progress"]
    llm2 = ScriptedLLM(json.dumps({"standalone": "How many patients?"}), ROUTE_SQL, "SELECT count(*) AS n FROM patients", "2.")
    events = list(stream_chat(make_deps(llm2, engines={"clinical": engine}, memory=memory), "again?", "clinician", None, "s"))
    steps = [e["data"].get("step") for e in events if e["event"] == "progress"]
    assert steps[0] == "contextualize"
    assert events[-1]["data"]["standalone_question"] == "How many patients?"
    assert len(memory.turns("s")) == 2


def test_rewrite_that_drops_the_name_is_still_refused(engine, memory):
    # Final review: smaller models drop Synthea digits ("Bob3" -> "Bob"); the code check must also look
    # at what the person actually typed.
    remember(memory, "What medications am I taking?", "You take lisinopril.", role="patient", patient="p1")
    llm = ScriptedLLM(json.dumps({"standalone": "What medications is Bob taking?"}))  # no route call scripted
    deps = make_deps(llm, engines={"clinical": engine}, memory=memory)
    deps.patient_names = {"p1": "Ann1 Lee2", "p2": "Bob3 Ray4"}
    assert run_chat(deps, "and what about Bob3?", "patient", "p1", "s").kind == "refusal"


# --- better follow-ups when Aether doesn't understand ------------------------------------------------
def test_clarify_options_carry_the_full_question_they_stand_for(engine, memory):
    clarify = {"kind": "clarify", "databases": [], "reason": "ambiguous",
               "clarify_question": "Revenue of what?", "options": ["Hospitals", "Insurers"],
               "option_questions": {"Hospitals": "Which hospital has the highest revenue?",
                                    "Insurers": "Which insurance company has the highest revenue?",
                                    "Doctors": "made up, not one of the options"}}
    result = run_chat(make_deps(ScriptedLLM(json.dumps(clarify)), engines={"clinical": engine}, memory=memory),
                      "What's the revenue?", "clinician", None, "s")
    assert result.options == ["Hospitals", "Insurers"]
    assert result.option_questions == {"Hospitals": "Which hospital has the highest revenue?",
                                       "Insurers": "Which insurance company has the highest revenue?"}


def test_router_is_told_to_write_full_questions_for_options(engine, memory):
    llm = ScriptedLLM('{"kind": "out_of_scope", "databases": [], "reason": "x"}')
    run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "hm", "clinician", None, "s")
    assert "option_questions" in llm.prompt_text(0) and "too vague" in llm.prompt_text(0)


BAD_SQL = ("SELECT a FROM patients", "SELECT b FROM patients", "SELECT c FROM patients")


def test_failed_query_offers_questions_it_can_answer(engine, memory):
    suggestions = {"suggestions": ["How many patients are there?", "How many female patients are there?"]}
    llm = ScriptedLLM(ROUTE_SQL, *BAD_SQL, json.dumps(suggestions))
    result = run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory),
                      "What's the patient churn by cohort?", "clinician", None, "s")
    assert result.kind == "clarification" and len(result.sql) == 3
    assert "Did you mean" in result.answer
    assert result.options == ["How many patients are there?", "How many female patients are there?", "None of these"]
    assert result.option_questions["How many patients are there?"] == "How many patients are there?"
    assert result.option_questions["None of these"] == ""
    prompt = llm.prompt_text()
    assert "patient churn by cohort" in prompt and "column" in prompt.lower()  # sees the question and what went wrong
    assert memory.turns("s")[-1].kind == "clarification"  # a typed reply is read as an answer to it


def test_failed_query_without_usable_suggestions_keeps_the_plain_message(engine, memory):
    llm = ScriptedLLM(ROUTE_SQL, *BAD_SQL, '{"suggestions": []}')
    result = run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "??", "clinician", None, "s")
    assert result.kind == "error" and "3 tries" in result.answer and result.options == []


def test_failed_query_suggestions_never_name_another_patient(engine, memory):
    suggestions = {"suggestions": ["What medications is Bob3 Ray4 taking?", "What medications am I taking?"]}
    llm = ScriptedLLM(ROUTE_SQL, *BAD_SQL, json.dumps(suggestions))
    deps = make_deps(llm, engines={"clinical": engine}, memory=memory)
    deps.patient_names = {"p1": "Ann1 Lee2", "p2": "Bob3 Ray4"}
    result = run_chat(deps, "my meds thing", "patient", "p1", "s")
    assert result.options == ["What medications am I taking?", "None of these"]
    assert "own records" in llm.prompt_text().lower()


@pytest.mark.parametrize("role,patient,expected", [("clinician", None, "How many patients are there?"),
                                                   ("patient", "p1", "What medications am I taking?")])
def test_out_of_scope_offers_example_questions(engine, memory, role, patient, expected):
    llm = ScriptedLLM('{"kind": "out_of_scope", "databases": [], "reason": "weather"}')
    result = run_chat(make_deps(llm, engines={"clinical": engine}, memory=memory), "Weather today?", role, patient, "s")
    assert result.kind == "out_of_scope" and expected in result.options and len(result.options) == 3
