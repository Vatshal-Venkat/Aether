"""Saved queries: the same question always runs the same SQL, so it always gives the same numbers.

Live (2026-11-19/20): the AI wrote the SQL afresh each time; the filter and the row shape varied between runs
(and between the main and the backup model), so the same question could come back with different results."""

import pytest
from sqlalchemy import create_engine, text

from app.graph.runner import run_chat
from app.graph.state import PlanStep, RouteDecision
from app.memory.saved_queries import SavedQuery, SavedQueryStore, SavedSql, normalize_question, worth_saving
from tests.fakes import ScriptedLLM, make_deps

ROUTE_SQL = '{"kind": "sql", "databases": ["clinical"], "reason": "count"}'
COUNT_SQL = "SELECT count(DISTINCT patient) AS n FROM conditions WHERE description LIKE '%diabetes%'"


def saved(sql=COUNT_SQL) -> SavedQuery:
    return SavedQuery(route=RouteDecision(kind="sql", databases=["clinical"]), plan=[PlanStep(db="clinical", goal="q")],
                      link=None, sql=[SavedSql(step=0, db="clinical", sql=sql)])


@pytest.fixture
def store(tmp_path):
    return SavedQueryStore(tmp_path / "saved.sqlite", version="v1")


# --- the store -----------------------------------------------------------------------------------------------
def test_same_question_in_other_words_case_or_punctuation_is_the_same_key():
    assert normalize_question("How many patients have diabetes?") == normalize_question("  how many PATIENTS have   diabetes ")
    assert normalize_question("Abe604's visits") != normalize_question("Abe's visits")  # names keep their digits


def test_save_and_reuse(store):
    store.save("clinician", "How many patients have diabetes?", saved())
    got = store.get("clinician", "how many patients have diabetes")
    assert got and got.sql[0].sql == COUNT_SQL and got.saved_at is not None


def test_kept_apart_by_role_and_by_rules_version(store, tmp_path):
    store.save("clinician", "How many patients have diabetes?", saved())
    assert store.get("patient", "How many patients have diabetes?") is None
    newer_rules = SavedQueryStore(tmp_path / "saved.sqlite", version="v2")  # glossary or SQL rules changed
    assert newer_rules.get("clinician", "How many patients have diabetes?") is None


def test_forget(store):
    store.save("clinician", "a?", saved())
    store.save("clinician", "b?", saved())
    assert store.forget("clinician", "a") == 1 and store.get("clinician", "a") is None
    assert store.forget() == 1 and store.count() == 0


def test_questions_about_now_are_not_saved():
    # "last month" written as fixed dates today would be wrong tomorrow.
    for q in ["How many visits last month?", "Who was admitted today?", "Visits this year", "most recent claims",
              "How many visits in the past 30 days?"]:
        assert not worth_saving(q), q
    assert worth_saving("How many patients have diabetes?")


# --- in the pipeline -------------------------------------------------------------------------------------------
@pytest.fixture
def engine():
    e = create_engine("sqlite://")
    with e.begin() as conn:
        conn.execute(text("CREATE TABLE conditions (patient TEXT, description TEXT)"))
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT)"))
        for p, d in [("p1", "Diabetes"), ("p1", "diabetes kidney"), ("p2", "Diabetes"), ("p3", "Asthma")]:
            conn.execute(text("INSERT INTO conditions VALUES (:p, :d)"), {"p": p, "d": d})
    return e


def ask(llm, engine, store, question="How many patients have diabetes?", role="clinician", patient_id=None):
    deps = make_deps(llm, engines={"clinical": engine}, saved_queries=store)
    return run_chat(deps, question, role, patient_id, "s")


def test_second_time_reuses_the_saved_sql_and_gives_the_same_result(engine, store):
    first = ask(ScriptedLLM(ROUTE_SQL, COUNT_SQL, "2 patients have diabetes."), engine, store)
    assert first.table.rows == [[2]] and not first.saved_query
    # Second time: no routing and no SQL writing by the AI — only the answer is written.
    llm = ScriptedLLM("2 patients have diabetes.")
    again = ask(llm, engine, store, question="how many patients have diabetes")
    assert again.saved_query and again.table.rows == [[2]]
    assert [s.query for s in again.sql] == [COUNT_SQL]
    assert len(llm.calls) == 1


def test_a_saved_query_that_no_longer_works_is_rewritten_and_replaced(engine, store):
    store.save("clinician", "How many patients have diabetes?", saved("SELECT nope FROM conditions"))
    fixed = "SELECT count(DISTINCT patient) AS n FROM conditions WHERE description LIKE '%diabetes%'"
    result = ask(ScriptedLLM(fixed, "2 patients have diabetes."), engine, store)
    assert result.table.rows == [[2]] and result.sql[0].error  # the saved try failed, the AI's rewrite worked
    assert store.get("clinician", "How many patients have diabetes?").sql[0].sql == fixed


def test_unverified_answers_errors_and_clarifications_are_not_saved(engine, store):
    ask(ScriptedLLM(ROUTE_SQL, COUNT_SQL, "7 patients.", "7 patients."), engine, store)  # 7 is not in the data
    assert store.count() == 0
    clarify = '{"kind": "clarify", "databases": [], "reason": "x", "clarify_question": "Which?", "options": ["A", "B"]}'
    ask(ScriptedLLM(clarify), engine, store, question="revenue?")
    assert store.count() == 0


def test_patient_mode_never_saves_sql_that_names_the_patient(engine, store):
    own = "SELECT count(*) AS n FROM conditions WHERE patient = 'p1'"
    ask(ScriptedLLM(ROUTE_SQL, own, "You have 2 diagnoses."), engine, store, question="How many diagnoses do I have?",
        role="patient", patient_id="p1")
    assert store.count() == 0


def test_without_a_store_nothing_changes(engine):
    result = ask(ScriptedLLM(ROUTE_SQL, COUNT_SQL, "2 patients have diabetes."), engine, None)
    assert result.table.rows == [[2]] and not result.saved_query


# --- follow-ups: the AI's rewrite ("show their names" -> a full question) varies too, so it is saved with the SQL ----
def test_a_follow_up_is_reused_by_previous_question_plus_what_was_typed(engine, store, tmp_path):
    import json

    from app.memory.store import ConversationStore, Turn

    memory = ConversationStore(tmp_path / "m.sqlite")
    names_sql = "SELECT DISTINCT patient FROM conditions WHERE description LIKE '%diabetes%'"
    for session in ("monday", "tuesday"):
        memory.add(Turn(session_id=session, role="clinician", patient_id=None, question="How many patients have diabetes?",
                        standalone="How many patients have diabetes?", answer="2 patients.", kind="answer"))
    rewrite = json.dumps({"standalone": "What are the names of the patients with diabetes?"})
    monday = make_deps(ScriptedLLM(rewrite, ROUTE_SQL, names_sql, "p1 and p2."), engines={"clinical": engine},
                       memory=memory, saved_queries=store)
    first = run_chat(monday, "show their names", "clinician", None, "monday")
    assert first.table.total_rows == 2 and not first.saved_query

    llm = ScriptedLLM("p1 and p2.")  # only the answer is written: no rewrite, no routing, no SQL by the AI
    tuesday = make_deps(llm, engines={"clinical": engine}, memory=memory, saved_queries=store)
    again = run_chat(tuesday, "Show their names", "clinician", None, "tuesday")
    assert again.saved_query and again.table.rows == first.table.rows
    assert again.standalone_question == "What are the names of the patients with diabetes?"
    assert len(llm.calls) == 1
