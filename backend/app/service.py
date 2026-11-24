"""The chat service: everything around the pipeline that a real service needs.

Plain English, for each question:
  1. Cache: a FIRST question (no conversation to depend on) that this same person asked recently is
     answered instantly from memory — no AI call. Follow-ups always run fresh.
  2. Queue: at most a couple of questions use the AI at the same time; others wait their turn.
  3. Pages: if the answer has a big table, keep all its rows here and send the first 100 plus a ticket.
  4. Logbook: write an audit record.
  5. Counters: update the live metrics.
The pipeline itself (route, SQL, labels, answer) is unchanged — this layer just wraps it.
"""

import hashlib
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from app.graph.deps import Deps
from app.graph.nodes.synthesize import NO_INDEX
from app.graph.runner import ChatResult, _remember, run_chat, stream_chat
from app.ops import Ops
from app.ops.audit import AuditEntry

log = logging.getLogger(__name__)


class ChatService:
    def __init__(self, deps: Deps, ops: Ops):
        self.deps, self.ops = deps, ops
        # "Schema version": if the tables or columns ever change, old cached answers no longer match.
        names = sorted(f"{t.name}.{c.name}" for t in deps.catalog.tables.values() for c in t.columns)
        self.schema_version = hashlib.sha1("|".join(names).encode()).hexdigest()[:10]

    # ---- helpers -------------------------------------------------------------------------------------
    def _key(self, question: str, role: str, patient_id: str | None) -> tuple:
        normal = " ".join(question.lower().split()).rstrip("?!. ")
        return (normal, role, patient_id, self.schema_version)

    @staticmethod
    def _cacheable_result(result: ChatResult) -> bool:
        """Only real answers are cached — not errors, refusals, clarifications, or temporary problems such as
        "drug information isn't loaded yet" (it would outlive building the library) — final review."""
        return result.kind == "answer" and result.answer != NO_INDEX and not any(s.error for s in result.sql)

    def _has_history(self, session_id: str, role: str, patient_id: str | None) -> bool:
        memory = self.deps.memory
        return bool(memory and memory.history(session_id, role, patient_id, limit=1))

    @contextmanager
    def _slot(self):
        """Wait for one of the few AI slots (the free tier can't take many questions at once)."""
        with self.ops.slots:
            self.ops.metrics.in_flight.inc()
            try:
                yield
            finally:
                self.ops.metrics.in_flight.dec()

    def _finish(self, result: ChatResult, question: str, role: str, patient_id: str | None,
                started: float, cached: bool) -> ChatResult:
        """Pages, logbook and counters — then the copy that goes back to the website."""
        seconds = time.monotonic() - started
        out = result.model_copy(deep=True, update={"cached": cached})
        if out.table and len(out.table.rows) > self.ops.results.page_size:
            rid = self.ops.results.put(out.table.columns, out.table.rows, owner=(role, patient_id))
            out.table = out.table.model_copy(update={"rows": out.table.rows[: self.ops.results.page_size], "result_id": rid})
        try:
            self.ops.audit.record(AuditEntry.from_result(result, role=role, patient_id=patient_id, question=question,
                                                         latency_s=seconds, cached=cached))
        except Exception:  # noqa: BLE001 — a logbook problem must never cost the user their answer
            log.exception("could not write the audit record")
        self.ops.metrics.observe(result, seconds, cached)
        return out

    def _from_cache(self, key: tuple, question: str, role: str, patient_id: str | None,
                    session_id: str, started: float) -> ChatResult | None:
        hit = self.ops.cache.get(key)
        if hit is None and self.deps.saved_queries is not None:
            # Semantic cache lookup: if a cleanly reworded question was answered recently
            try:
                match = self.deps.saved_queries.similar(role, question, owner=patient_id)
                if match and match.kind == "same":
                    alt_key = self._key(match.question, role, patient_id)
                    hit = self.ops.cache.get(alt_key)
                    if hit is not None:
                        hit = hit.model_copy(update={"standalone_question": match.question})
            except Exception:  # noqa: BLE001
                pass
        if hit is None:
            self.ops.metrics.cache_miss()
            return None
        _remember(self.deps, question, role, patient_id, session_id, hit)  # the hit joins this conversation
        return self._finish(hit, question, role, patient_id, started, cached=True)

    # ---- the two ways to ask ---------------------------------------------------------------------------
    def answer(self, question: str, role: str, patient_id: str | None, session_id: str,
               runner: Callable[..., ChatResult] = run_chat) -> ChatResult:
        patient_id = patient_id if role == "patient" else None  # a clinician has no patient id (final review)
        started = time.monotonic()
        cacheable = not self._has_history(session_id, role, patient_id)
        key = self._key(question, role, patient_id)
        if cacheable and (hit := self._from_cache(key, question, role, patient_id, session_id, started)):
            return hit
        with self._slot():
            result = runner(self.deps, question, role, patient_id, session_id)
        if cacheable and self._cacheable_result(result):
            self.ops.cache.put(key, result)
        return self._finish(result, question, role, patient_id, started, cached=False)

    def stream(self, question: str, role: str, patient_id: str | None, session_id: str,
               streamer: Callable[..., Iterator[dict]] = stream_chat) -> Iterator[dict]:
        patient_id = patient_id if role == "patient" else None  # a clinician has no patient id (final review)
        started = time.monotonic()
        cacheable = not self._has_history(session_id, role, patient_id)
        key = self._key(question, role, patient_id)
        if cacheable and (hit := self._from_cache(key, question, role, patient_id, session_id, started)):
            yield {"event": "final", "data": hit.model_dump()}
            return
        with self._slot():
            for event in streamer(self.deps, question, role, patient_id, session_id):
                if event["event"] == "final":
                    result = ChatResult.model_validate(event["data"])
                    if cacheable and self._cacheable_result(result):
                        self.ops.cache.put(key, result)
                    out = self._finish(result, question, role, patient_id, started, cached=False)
                    yield {"event": "final", "data": out.model_dump()}
                elif event["event"] == "error":
                    self._finish(ChatResult(kind="error", answer=event["data"]["message"]), question, role,
                                 patient_id, started, cached=False)
                    yield event
                else:
                    yield event
