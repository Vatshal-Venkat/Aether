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

from app.memory.store import ConversationStore, Turn
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
    route: str | None = None   # what the router decided: sql / rag / hybrid / clarify / refuse / out_of_scope
    standalone_question: str | None = None  # a follow-up, rewritten as a full question ("Understood as: ...")
    options: list[str] = []    # a clarifying question's suggested answers (one click each on the website)
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
        memory=ConversationStore(settings.memory_path),  # conversation turns, for follow-up questions
        patient_names={p["id"]: p["name"] for p in list_patients(engines["clinical"])},
        provider_names=list_provider_names(engines["billing"]),
    )


def is_rate_limit(exc: Exception) -> bool:
    """Did the AI provider say "too many requests" (HTTP 429)? Works for Groq, Gemini and plain HTTP errors."""
    if "ratelimit" in type(exc).__name__.lower():
        return True
    for attr in ("status_code", "code"):
        if getattr(exc, attr, None) == 429:
            return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


def friendly_error(exc: Exception) -> str:
    """Pick a message that points the user in the right direction. Only a real rate limit says
    "rate-limited": the accuracy report counts those questions as "not run" instead of wrong."""
    if isinstance(exc, LLMOutputError):
        return "The AI gave a reply I couldn't use. Please try again, or try rephrasing your question."
    if isinstance(exc, SQLAlchemyError):
        return "The database is unavailable right now. Please try again shortly."
    if is_rate_limit(exc):
        return "The AI service is rate-limited right now (free-tier limit). Please try again in a minute."
    if isinstance(exc, _transient_errors()):
        return "The AI service is unavailable right now. Please try again in a minute."
    return "Something went wrong while answering. The details are in the server log."


def _initial_state(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str) -> dict:
    """The starting notepad, including this person's recent turns (if conversation memory is on)."""
    history = []
    if deps.memory is not None:
        history = [{"question": t.question, "answer": t.answer, "kind": t.kind}
                   for t in deps.memory.history(session_id, role, patient_id, deps.settings.memory_turns)]
    return {"question": question, "role": role, "patient_id": patient_id, "session_id": session_id,
            "history": history, "attempts": [], "timings": {}}


def _remember(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str,
              result: ChatResult) -> None:
    """Save this turn so the next question in the conversation can refer back to it."""
    if deps.memory is None:
        return
    try:
        deps.memory.add(Turn(session_id=session_id, role=role, patient_id=patient_id, question=question,
                             standalone=result.standalone_question or question, answer=result.answer, kind=result.kind))
    except Exception:  # noqa: BLE001 — losing one memory note must never break the answer
        log.exception("could not save conversation turn")


def run_chat(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str) -> ChatResult:
    try:
        final = build_graph(deps).invoke(_initial_state(deps, question, role, patient_id, session_id))
        result = _package(final)
    except Exception as exc:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        log.exception("chat pipeline failed")
        result = ChatResult(kind="error", answer=friendly_error(exc))
    _remember(deps, question, role, patient_id, session_id, result)
    return result


# Steps worth telling the website about (bookkeeping steps like next_step are skipped).
REPORTED_STEPS = {"contextualize", "route", "plan", "inject_schema", "generate_sql", "validate", "row_filter", "execute",
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
        stream = build_graph(deps).stream(_initial_state(deps, question, role, patient_id, session_id),
                                          stream_mode=["tasks", "values"])
        for mode, chunk in stream:
            if mode == "values":
                final = chunk
            elif "input" in chunk and chunk.get("name") in REPORTED_STEPS:  # a step is starting
                step_input = chunk["input"] or {}
                if chunk["name"] == "contextualize" and not step_input.get("history"):
                    continue  # nothing to recall: the step does nothing, so don't announce it
                yield {"event": "progress", "data": _progress(chunk["name"], step_input)}
        result = _package(final)
    except Exception as exc:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        log.exception("chat pipeline failed")
        result = ChatResult(kind="error", answer=friendly_error(exc))
        _remember(deps, question, role, patient_id, session_id, result)
        yield {"event": "error", "data": {"message": result.answer}}
        return
    _remember(deps, question, role, patient_id, session_id, result)
    yield {"event": "final", "data": result.model_dump()}


def _package(final: dict) -> ChatResult:
    """The pipeline's final notepad -> the tidy result the API returns."""
    return ChatResult(
        answer=final["answer"],
        kind=final["kind"],
        route=final["route"].kind if final.get("route") else None,
        standalone_question=final["question"] if final.get("original_question") else None,
        options=final["route"].options if final.get("route") and final.get("kind") == "clarification" else [],
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
