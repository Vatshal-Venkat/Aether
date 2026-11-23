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


# --- past conversations (the website's history list) --------------------------------------------------------
def test_full_answers_are_kept_for_the_history_view(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1, answer="x" * 2000))
    assert len(store.turns("s1")[0].answer) == 2000                     # shown in full when reopened
    assert len(store.history("s1", "clinician", None)[0].answer) <= 400  # the AI's context stays short


def test_past_conversations_newest_first_with_their_first_question(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1, session="old"))
    store.add(turn(2, session="old"))
    store.add(turn(3, session="new"))
    convs = store.sessions("clinician", None)
    assert [c.session_id for c in convs] == ["new", "old"]
    assert convs[1].title == "q1" and convs[1].questions == 2 and convs[1].updated_at >= convs[1].started_at


def test_each_person_sees_only_their_own_conversations(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1, session="c", role="clinician"))
    store.add(turn(2, session="a", role="patient", patient="p1"))
    store.add(turn(3, session="b", role="patient", patient="p2"))
    assert [c.session_id for c in store.sessions("clinician", None)] == ["c"]
    assert [c.session_id for c in store.sessions("patient", "p1")] == ["a"]
    assert store.sessions("patient", "p3") == []


def test_failed_turns_alone_do_not_make_a_conversation(tmp_path):
    store = ConversationStore(tmp_path / "m.sqlite")
    store.add(turn(1, session="broken", kind="error"))
    assert store.sessions("clinician", None) == []
