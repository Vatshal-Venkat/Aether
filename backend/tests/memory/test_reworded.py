"""Reworded questions: very close rewordings reuse the saved query silently; less certain ones ask "Do you mean...?".

Similarity scores alone can't be trusted (measured with the real local model, 2026-11-20): "How many patients do NOT
have diabetes?" scored 0.912 and "How many FEMALE patients..." 0.891 against "How many patients have diabetes?", while
the true rewording "number of diabetic patients" scored only 0.876. So code checks the words too."""

import pytest
from sqlalchemy import create_engine, text

from app.graph.runner import run_chat
from app.memory.saved_queries import SavedQueryStore, match_kind
from app.memory.store import ConversationStore
from tests.fakes import ScriptedLLM, make_deps

BASE = "How many patients have diabetes?"


@pytest.mark.parametrize("asked,score,expected", [
    ("How many people have diabetes?", 0.933, "same"),
    ("How many patients are diabetic?", 0.916, "same"),
    ("number of diabetic patients", 0.876, "same"),
    ("How many patients have been diagnosed with diabetes?", 0.938, "same"),
    ("count the patients with diabetes", 0.798, "same"),
    ("How many female patients have diabetes?", 0.891, "ask"),       # one more filter: not sure -> ask
    ("How many diabetics are there?", 0.820, "ask"),
    ("How many patients have prediabetes?", 0.830, "ask"),
    ("How many patients do not have diabetes?", 0.912, None),         # negation: never the same question
    ("How many patients don't have diabetes?", 0.910, None),
    ("How many patients had diabetes last year?", 0.876, None),       # about "now": never matched
    ("list the patients with diabetes", 0.745, None),                 # too far
    ("How many patients have asthma?", 0.459, None),
])
def test_match_kind_on_measured_scores(asked, score, expected):
    assert match_kind(asked, BASE, score) == expected


@pytest.mark.parametrize("asked,saved,score,expected", [
    ("Which insurer has the most customers?", "Which insurance company has the most customers?", 0.955, "same"),
    ("Which insurance company has the fewest customers?", "Which insurance company has the most customers?", 0.917, None),
    ("Top 5 insurance companies by customers", "Top 10 insurance companies by customers", 0.97, None),
    ("Which insurance company has the most revenue?", "Which insurance company has the most customers?", 0.821, "ask"),
    ("Which patient saw the most doctors?", "Which doctor saw the most patients?", 0.95, "ask"),  # same words, swapped
    ("How many male patients are there?", "How many female patients are there?", 0.95, None),
])
def test_match_kind_guards(asked, saved, score, expected):
    assert match_kind(asked, saved, score) == expected


# --- in the pipeline, with a fake similarity model ---------------------------------------------------------------
def _key(t: str) -> str:
    return t.lower().strip(" ?")


class FakeEmbed:
    """2-d vectors: BASE is [1, 0]; a question listed in `near` gets exactly that similarity to it; others 0."""

    def __init__(self, near: dict[str, float]):
        self.near = {_key(k): v for k, v in near.items()}

    def __call__(self, texts):
        out = []
        for t in texts:
            s = 1.0 if _key(t) == _key(BASE) else self.near.get(_key(t), 0.0)
            out.append([s, (1 - s * s) ** 0.5])
        return out


ROUTE_SQL = '{"kind": "sql", "databases": ["clinical"], "reason": "count"}'
COUNT_SQL = "SELECT count(DISTINCT patient) AS n FROM conditions WHERE description LIKE '%diabetes%'"
FRESH_SQL = "SELECT count(DISTINCT patient) AS n FROM conditions WHERE description LIKE '%iabetes%'"
FEMALE = "How many female patients have diabetes?"


@pytest.fixture
def engine():
    e = create_engine("sqlite://")
    with e.begin() as conn:
        conn.execute(text("CREATE TABLE conditions (patient TEXT, description TEXT)"))
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT)"))
        for p, d in [("p1", "Diabetes"), ("p2", "Diabetes"), ("p3", "Asthma")]:
            conn.execute(text("INSERT INTO conditions VALUES (:p, :d)"), {"p": p, "d": d})
    return e


@pytest.fixture
def world(engine, tmp_path):
    embed = FakeEmbed({"How many people have diabetes": 0.933, FEMALE: 0.891,
                       "How many patients do not have diabetes": 0.912})
    store = SavedQueryStore(tmp_path / "saved.sqlite", version="v1", embed=embed)
    memory = ConversationStore(tmp_path / "m.sqlite")

    def ask(llm, question, session="s", role="clinician", patient_id=None):
        deps = make_deps(llm, engines={"clinical": engine}, memory=memory, saved_queries=store)
        return run_chat(deps, question, role, patient_id, session)

    ask(ScriptedLLM(ROUTE_SQL, COUNT_SQL, "2 patients have diabetes."), BASE, session="first")
    return ask


def test_a_very_close_rewording_reuses_the_saved_query_and_says_how_it_was_read(world):
    llm = ScriptedLLM("2 patients have diabetes.")  # only the answer: no routing, no SQL writing
    result = world(llm, "How many people have diabetes?", session="new")
    assert result.saved_query and result.table.rows == [[2]] and [s.query for s in result.sql] == [COUNT_SQL]
    assert result.standalone_question == BASE  # "Understood as: How many patients have diabetes?"
    assert len(llm.calls) == 1


def test_a_less_certain_one_asks_first_and_costs_no_ai_call(world):
    result = world(ScriptedLLM(), FEMALE, session="new")  # any AI call would fail the test
    assert result.kind == "clarification" and BASE in result.answer
    assert result.options == ["Yes, the same question", "No, something different"]
    assert result.option_questions == {"Yes, the same question": BASE, "No, something different": FEMALE}


def test_yes_reuses_the_saved_query_without_rewriting_anything(world):
    world(ScriptedLLM(), FEMALE, session="c")
    llm = ScriptedLLM("2 patients have diabetes.")
    result = world(llm, BASE, session="c")  # the "Yes" button sends the saved question
    assert result.saved_query and result.table.rows == [[2]] and len(llm.calls) == 1


def test_no_answers_it_fresh_and_never_asks_again(world):
    world(ScriptedLLM(), FEMALE, session="d")
    llm = ScriptedLLM(ROUTE_SQL, FRESH_SQL, "2 patients.")  # no rewrite call: the "No" button sends a full question
    result = world(llm, FEMALE, session="d")
    assert result.kind == "answer" and not result.saved_query and [s.query for s in result.sql] == [FRESH_SQL]


def test_a_negation_is_never_matched(world):
    result = world(ScriptedLLM(ROUTE_SQL, FRESH_SQL, "1 patient."), "How many patients do not have diabetes?", session="e")
    assert result.kind == "answer" and not result.saved_query


def test_patients_are_only_offered_their_own_earlier_questions(world):
    first = world(ScriptedLLM(ROUTE_SQL, COUNT_SQL, "2."), BASE, session="p1s", role="patient", patient_id="p1")
    assert first.kind == "answer"
    mine = world(ScriptedLLM(), FEMALE, session="p1s2", role="patient", patient_id="p1")
    assert mine.kind == "clarification"  # p1 is offered p1's own earlier question
    other = world(ScriptedLLM(ROUTE_SQL, COUNT_SQL, "2."), FEMALE, session="p2s", role="patient", patient_id="p2")
    assert other.kind == "answer"  # p1's wording is never shown to p2
