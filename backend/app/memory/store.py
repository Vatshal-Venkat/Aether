"""Conversation memory — so "how many of THEM are female?" can mean the patients from the last answer.

Plain English: after each question we write a short note: the session it belongs to, who asked
(clinician, or which patient), the question, how Aether understood it, the start of the answer,
and what kind of reply it was. The next question in the same conversation reads the last few notes.

Privacy: notes are looked up by session AND role AND patient. If the same session id were reused
for a different patient (or for the clinician view), it would find nothing. Only the question and a
answer text are kept (the AI gets only the first 400 characters back as context) — never the result tables.

Only answers and clarifying questions are offered as context; refusals and errors are kept for the
history view but would only confuse the next step.

Stored in a small SQLite file (backend/data/memory.sqlite, not uploaded to git).
"""

import datetime as dt
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, func, insert, select

MAX_ANSWER_CHARS = 400      # what the AI gets back as context
MAX_STORED_CHARS = 8000     # what is kept, so a reopened conversation shows the whole answer
CONTEXT_KINDS = ("answer", "clarification")

_meta = MetaData()
_turns = Table(
    "turns", _meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), index=True, nullable=False),
    Column("role", String(16), nullable=False),
    Column("patient_id", String(64)),
    Column("question", Text, nullable=False),
    Column("standalone", Text, nullable=False),
    Column("answer", Text, nullable=False),
    Column("kind", String(16), nullable=False),
    Column("created_at", DateTime, nullable=False),
)


class Turn(BaseModel):
    session_id: str
    role: str
    patient_id: str | None
    question: str          # what the person typed
    standalone: str        # how Aether understood it (the follow-up rewritten as a full question)
    answer: str
    kind: str
    created_at: dt.datetime | None = None


class Conversation(BaseModel):
    """One past conversation in the history list."""
    session_id: str
    title: str            # its first question
    questions: int
    started_at: dt.datetime
    updated_at: dt.datetime


class ConversationStore:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        _meta.create_all(self.engine)

    def add(self, turn: Turn) -> None:
        row = turn.model_dump()
        row["answer"] = row["answer"][:MAX_STORED_CHARS]
        row["created_at"] = turn.created_at or dt.datetime.now(dt.timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(insert(_turns).values(**row))

    def history(self, session_id: str, role: str, patient_id: str | None, limit: int = 3) -> list[Turn]:
        """The last `limit` usable turns of THIS person's conversation, oldest first."""
        patient_match = _turns.c.patient_id.is_(None) if patient_id is None else _turns.c.patient_id == patient_id
        stmt = (select(_turns).where(_turns.c.session_id == session_id, _turns.c.role == role, patient_match,
                                     _turns.c.kind.in_(CONTEXT_KINDS))
                .order_by(_turns.c.id.desc()).limit(limit))
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        turns = [Turn(**{k: r[k] for k in Turn.model_fields}) for r in reversed(rows)]
        return [t.model_copy(update={"answer": t.answer[:MAX_ANSWER_CHARS]}) for t in turns]

    def sessions(self, role: str, patient_id: str | None, limit: int = 30) -> list["Conversation"]:
        """THIS person's past conversations, newest first: the website's "Past conversations" list.
        Scoped like history(): the clinician view sees clinician conversations, a patient only their own."""
        patient_match = _turns.c.patient_id.is_(None) if patient_id is None else _turns.c.patient_id == patient_id
        mine = (_turns.c.role == role, patient_match, _turns.c.kind != "error")
        stmt = (select(_turns.c.session_id, func.min(_turns.c.id).label("first"), func.count().label("n"),
                       func.min(_turns.c.created_at).label("started"), func.max(_turns.c.created_at).label("updated"))
                .where(*mine).group_by(_turns.c.session_id).order_by(func.max(_turns.c.id).desc()).limit(limit))
        with self.engine.connect() as conn:
            groups = conn.execute(stmt).mappings().all()
            titles = dict(conn.execute(select(_turns.c.id, _turns.c.question)
                                       .where(_turns.c.id.in_([g["first"] for g in groups]))).all()) if groups else {}
        return [Conversation(session_id=g["session_id"], title=titles.get(g["first"], ""), questions=g["n"],
                             started_at=g["started"], updated_at=g["updated"]) for g in groups]

    def turns(self, session_id: str, role: str | None = None, patient_id: str | None = None) -> list[Turn]:
        """Every turn of a session (for the history view), oldest first. With a role, only that person's
        turns (same scoping as history(): another patient or the clinician view sees nothing)."""
        stmt = select(_turns).where(_turns.c.session_id == session_id)
        if role is not None:
            patient_match = _turns.c.patient_id.is_(None) if patient_id is None else _turns.c.patient_id == patient_id
            stmt = stmt.where(_turns.c.role == role, patient_match)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt.order_by(_turns.c.id)).mappings().all()
        return [Turn(**{k: r[k] for k in Turn.model_fields}) for r in rows]
