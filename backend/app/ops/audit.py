"""The audit log — a record of every question and what Aether did with it.

Plain English: like a logbook at a front desk. For every request we write down when, who asked
(clinician, or which patient), the question and how it was understood, how it was routed, every SQL
query that ran (on which database, and any error), how many rows came back, whether the answer came
from the cache, whether it worked, and how long it took. It lives in a local SQLite file
(backend/data/audit.sqlite, not uploaded to git).

Because there is no login, the page that READS this log (/api/audit) is switched off unless you turn
it on (ENABLE_AUDIT_API=true): otherwise anyone could read every patient's questions.
"""

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine, insert, select

from app.graph.runner import ChatResult

_meta = MetaData()
_audit = Table(
    "audit", _meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("role", String(16), nullable=False),
    Column("patient_id", String(64)),
    Column("question", Text, nullable=False),
    Column("standalone", Text),
    Column("route", String(16)),
    Column("kind", String(16), nullable=False),
    Column("sql", Text, nullable=False),        # JSON list of {db, query, error}
    Column("row_count", Integer, nullable=False),
    Column("cached", Boolean, nullable=False),
    Column("status", String(8), nullable=False),
    Column("latency_s", Float, nullable=False),
)


class AuditEntry(BaseModel):
    role: str
    patient_id: str | None
    question: str
    standalone: str | None
    route: str | None
    kind: str
    sql: list[dict[str, Any]]
    row_count: int
    cached: bool
    status: str               # "ok" or "error"
    latency_s: float
    timestamp: dt.datetime | None = None

    @classmethod
    def from_result(cls, result: ChatResult, *, role: str, patient_id: str | None, question: str,
                    latency_s: float, cached: bool) -> "AuditEntry":
        return cls(role=role, patient_id=patient_id, question=question, standalone=result.standalone_question,
                   route=result.route, kind=result.kind, sql=[s.model_dump() for s in result.sql],
                   row_count=result.table.total_rows if result.table else 0, cached=cached,
                   status="error" if result.kind == "error" else "ok", latency_s=round(latency_s, 3))


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._engine = None  # the file is created on first use, not when the app starts
        self._lock = threading.Lock()

    @property
    def engine(self):
        # Create the table BEFORE anyone can use the engine: when the first requests arrive together, a
        # second thread could otherwise write before the table exists ("no such table") — final review.
        with self._lock:
            if self._engine is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False, "timeout": 15})
                _meta.create_all(engine)
                self._engine = engine
        return self._engine

    def record(self, entry: AuditEntry) -> None:
        row = entry.model_dump()
        row["sql"] = json.dumps(row["sql"])
        row["timestamp"] = entry.timestamp or dt.datetime.now(dt.timezone.utc)
        with self.engine.begin() as conn:
            conn.execute(insert(_audit).values(**row))

    def recent(self, limit: int = 50) -> list[AuditEntry]:
        """Newest first."""
        with self.engine.connect() as conn:
            rows = conn.execute(select(_audit).order_by(_audit.c.id.desc()).limit(limit)).mappings().all()
        return [AuditEntry(**{**{k: r[k] for k in AuditEntry.model_fields}, "sql": json.loads(r["sql"])}) for r in rows]
