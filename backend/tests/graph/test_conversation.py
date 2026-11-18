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
