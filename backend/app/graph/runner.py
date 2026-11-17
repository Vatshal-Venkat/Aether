"""Run one question through the pipeline and package the result for the API.

Plain English: takes a question plus "who is asking", runs the flowchart, and returns a
tidy result: the answer, what kind of answer it is, every SQL attempt (so you can see the
self-correction happen), the sources, the result table and how long each step took.
If the AI service is down or rate-limited, you get a friendly message instead of a crash.
"""

import logging
from collections.abc import Iterator

from pydantic import BaseModel

from app.config import Settings
from app.db.catalog import build_catalog
from app.db.engines import DbName, get_engine
from app.db.patients import list_patients, list_provider_names
from app.graph.build import build_graph
from app.graph.deps import Deps
from app.graph.state import AnswerKind, QueryResult
from sqlalchemy.exc import SQLAlchemyError

from app.rag.store import DrugLabelStore
from app.llm.client import LLMOutputError, _transient_errors, get_chat_model
from app.semantic.glossary import load_glossary

log = logging.getLogger(__name__)


class SqlRecord(BaseModel):
    db: DbName
    query: str
    error: str | None = None


class DocumentRef(BaseModel):
    """A drug-label passage the answer was based on, with a link to the official label."""
    label: str
    source_url: str
    excerpt: str


class ChatResult(BaseModel):
    answer: str
    kind: AnswerKind
    sql: list[SqlRecord] = []
    sources: list[str] = []
    table: QueryResult | None = None
    unverified_numbers: list[str] = []
    documents: list[DocumentRef] = []
    timings: dict[str, float] = {}


def build_deps(settings: Settings) -> Deps:
    engines: dict[DbName, object] = {"clinical": get_engine("clinical"), "billing": get_engine("billing")}
    glossary = load_glossary()
    return Deps(
        settings=settings,
        llm=get_chat_model(settings),
        catalog=build_catalog(engines, glossary),
        glossary=glossary,
        engines=engines,
        store=DrugLabelStore.open(settings.chroma_dir),  # None if not built: SQL questions still work
        patient_names={p["id"]: p["name"] for p in list_patients(engines["clinical"])},
        provider_names=list_provider_names(engines["billing"]),
    )


def friendly_error(exc: Exception) -> str:
    """Pick a message that points the user in the right direction."""
    if isinstance(exc, LLMOutputError):
        return "The AI gave a reply I couldn't use. Please try again, or try rephrasing your question."
    if isinstance(exc, SQLAlchemyError):
        return "The database is unavailable right now. Please try again shortly."
    if isinstance(exc, _transient_errors()):
        return "The AI service is unavailable or rate-limited right now. Please try again in a minute."
    return "Something went wrong while answering. The details are in the server log."


def _initial_state(question: str, role: str, patient_id: str | None, session_id: str) -> dict:
    return {"question": question, "role": role, "patient_id": patient_id, "session_id": session_id,
            "attempts": [], "timings": {}}


def run_chat(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str) -> ChatResult:
    try:
        final = build_graph(deps).invoke(_initial_state(question, role, patient_id, session_id))
    except Exception as exc:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        log.exception("chat pipeline failed")
        return ChatResult(kind="error", answer=friendly_error(exc))
    return _package(final)


# Steps worth telling the website about (bookkeeping steps like next_step are skipped).
REPORTED_STEPS = {"route", "plan", "inject_schema", "generate_sql", "validate", "row_filter", "execute",
                  "merge", "retrieve", "synthesize", "verify_numbers"}
STEPS_WITH_DB = {"inject_schema", "generate_sql", "validate", "row_filter", "execute"}


def _progress(name: str, step_input: dict) -> dict:
    """What the website needs to know about a step that is starting: which step, on which database,
    and — for SQL writing — whether this is a retry after a failed try."""
    data: dict = {"step": name}
    if name in STEPS_WITH_DB and step_input.get("db"):
        data["db"] = step_input["db"]
    if name == "generate_sql":
        step = step_input.get("step", 0)
        data["retry"] = any(a.get("step", 0) == step for a in step_input.get("attempts") or [])
    return data


def stream_chat(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str) -> Iterator[dict]:
    """Like run_chat, but reports each step as it starts ("progress" events), then the result ("final").

    Plain English: instead of waiting in silence, the backend says "now writing SQL", "now querying
    billing_db"... so the website can show what is happening (the thinking orbs change rhythm)."""
    final: dict | None = None
    try:
        stream = build_graph(deps).stream(_initial_state(question, role, patient_id, session_id),
                                          stream_mode=["tasks", "values"])
        for mode, chunk in stream:
            if mode == "values":
                final = chunk
            elif "input" in chunk and chunk.get("name") in REPORTED_STEPS:  # a step is starting
                yield {"event": "progress", "data": _progress(chunk["name"], chunk["input"] or {})}
        yield {"event": "final", "data": _package(final).model_dump()}
    except Exception as exc:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        log.exception("chat pipeline failed")
        yield {"event": "error", "data": {"message": friendly_error(exc)}}


def _package(final: dict) -> ChatResult:
    """The pipeline's final notepad -> the tidy result the API returns."""
    return ChatResult(
        answer=final["answer"],
        kind=final["kind"],
        # One record per try, on its own database; shows what really ran (with any row filter added).
        sql=[SqlRecord(db=a.get("db") or final.get("db", "clinical"), query=a.get("executed") or a["sql"],
                       error=a["error"]) for a in final.get("attempts") or []],
        sources=final.get("sources") or [],
        table=final.get("result"),
        unverified_numbers=final.get("unverified_numbers") or [],
        documents=[DocumentRef(label=c.label, source_url=c.source_url, excerpt=c.text[:300])
                   for c in final.get("chunks") or []],
        timings=final.get("timings") or {},
    )
