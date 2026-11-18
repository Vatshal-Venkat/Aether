"""The conversation memory: turns stored per session, role and patient — never shared across them."""

from app.memory.store import ConversationStore, Turn


def turn(n, session="s1", role="clinician", patient=None, kind="answer", answer=None):
    return Turn(session_id=session, role=role, patient_id=patient, question=f"q{n}", standalone=f"q{n} (standalone)",
                answer=answer or f"a{n}", kind=kind)


def test_history_oldest_first_and_limited(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    for n in range(5):
        store.add(turn(n))
    hist = store.history("s1", "clinician", None, limit=3)
    assert [t.question for t in hist] == ["q2", "q3", "q4"]


def test_history_scoped_to_role_and_patient(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1, role="patient", patient="p1"))
    store.add(turn(2, role="patient", patient="p2"))
    store.add(turn(3, role="clinician"))
    assert [t.question for t in store.history("s1", "patient", "p1")] == ["q1"]
    assert [t.question for t in store.history("s1", "patient", "p2")] == ["q2"]
    assert [t.question for t in store.history("s1", "clinician", None)] == ["q3"]
    assert store.history("other-session", "patient", "p1") == []


def test_only_answers_and_clarifications_are_context(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1))
    store.add(turn(2, kind="error"))
    store.add(turn(3, kind="refusal"))
    store.add(turn(4, kind="clarification"))
    assert [t.question for t in store.history("s1", "clinician", None)] == ["q1", "q4"]
    assert len(store.turns("s1")) == 4  # but every turn is kept for the history view


def test_long_answers_are_truncated(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1, answer="x" * 2000))
    assert len(store.history("s1", "clinician", None)[0].answer) <= 400


def test_survives_reopen(tmp_path):
    ConversationStore(tmp_path / "m.sqlite").add(turn(1))
    assert ConversationStore(tmp_path / "m.sqlite").history("s1", "clinician", None)[0].question == "q1"
