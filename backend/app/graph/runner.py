"""Run one question through the pipeline and package the result for the API.

Plain English: takes a question plus "who is asking", runs the flowchart, and returns a
tidy result: the answer, what kind of answer it is, every SQL attempt (so you can see the
self-correction happen), the sources, the result table and how long each step took.
If the AI service is down or rate-limited, you get a friendly message instead of a crash.
"""

import logging
import math
from datetime import date
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




from app.memory.saved_queries import SavedQuery, SavedQueryStore, SavedSql, follow_up_key, rules_version, worth_saving
from app.memory.store import ConversationStore, Turn
from app.rag.rerank import load_reranker
from app.rag.store import DrugLabelStore
from app.llm.client import (MODELS_USED_KEY, LLMOutputError, _transient_errors, chat_models, daily_limit_rest,
                            get_chat_model, get_fast_model, model_name, usage_ledger)
from app.llm.prompts import CONTEXTUALIZE_SYSTEM, plan_system, route_system, sql_system
from app.semantic.glossary import GLOSSARY_PATH, load_glossary
from app.terminology.client import TerminologyClient

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
    option_questions: dict[str, str] = {}  # optional: the exact question each option sends ("" = none, ask again)
    cached: bool = False       # answered instantly from the answer cache (Plan 5)
    sql: list[SqlRecord] = []
    sources: list[str] = []
    table: QueryResult | None = None
    unverified_numbers: list[str] = []
    documents: list[DocumentRef] = []
    timings: dict[str, float] = {}
    model_notice: str | None = None
    models_used: list[str] = []  # every AI model that wrote part of this answer, in order
    saved_query: bool = False  # the SQL was reused from the first time this question was asked (same numbers)  # "gpt-oss-120b has used up its free daily limit, so ... the backup model ..."


def build_deps(settings: Settings) -> Deps:
    settings.ensure_data_dir()
    engines: dict[DbName, object] = {"clinical": get_engine("clinical"), "billing": get_engine("billing")}
    glossary = load_glossary()
    ledger = usage_ledger(settings)
    model = embedding_model()  # ONE copy (~110 MB) shared by the drug library and saved queries: Render has 512 MB
    return Deps(
        settings=settings,
        llm=get_chat_model(settings, ledger),
        fast_llm=get_fast_model(settings, ledger),
        models=[model_name(m) for m in chat_models(settings)],
        usage=ledger,
        catalog=build_catalog(engines, glossary),
        glossary=glossary,
        engines=engines,
        store=DrugLabelStore.open(settings.chroma_dir, embedding_function=model),  # None if not built
        reranker=load_reranker(settings),  # None if switched off or unavailable: passages keep the search order
        memory=ConversationStore(settings.memory_path),  # conversation turns, for follow-up questions
        saved_queries=(SavedQueryStore(settings.saved_queries_path, saved_queries_version(glossary), question_embedder(model))
                       if settings.saved_queries else None),  # same question -> same SQL -> same numbers
        patient_names={p["id"]: p["name"] for p in list_patients(engines["clinical"])},
        provider_names=list_provider_names(engines["billing"]),
        terminology=(TerminologyClient(settings.terminology_mcp_url or None) if settings.terminology_mcp else None),
    )


def embedding_model():
    """The small local model (all-MiniLM-L6-v2), loaded on first use. ChromaDB's "default" function — the one the
    drug library was built with, so it can be handed to it without a conflict. None if unavailable."""
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        return DefaultEmbeddingFunction()
    except Exception:  # noqa: BLE001
        log.warning("embedding model unavailable")
        return None


def question_embedder(model):
    """Scores how alike two questions are, for reworded questions; None if no model (exact matches still work)."""
    if model is None:
        log.warning("question matching model unavailable; only exact repeat questions reuse saved queries")
        return None
    return lambda texts: [list(map(float, v)) for v in model(list(texts))]


def saved_queries_version(glossary) -> str:
    """Fingerprint of what shapes the SQL — glossary, router / plan / SQL rules (today's date left out). When one
    of them changes, saved queries made under the old rules are no longer used."""
    today = date.today().isoformat()
    texts = [GLOSSARY_PATH.read_text(encoding="utf-8"), CONTEXTUALIZE_SYSTEM, route_system("clinician"), route_system("patient"),
             plan_system(glossary.links)]
    texts += [sql_system(d, r).replace(today, "") for d in ("PostgreSQL", "MySQL") for r in ("clinician", "patient")]
    return rules_version(*texts)


def is_rate_limit(exc: Exception) -> bool:
    """Did the AI provider say "too many requests" (HTTP 429)? Works for Groq, Gemini and plain HTTP errors."""
    if "ratelimit" in type(exc).__name__.lower():
        return True
    for attr in ("status_code", "code"):
        if getattr(exc, attr, None) == 429:
            return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


def _short(model: str) -> str:
    return model.split("/")[-1]  # "openai/gpt-oss-120b" -> "gpt-oss-120b"


def _minutes(seconds: float) -> str:
    minutes = max(1, math.ceil(seconds / 60))
    return f"{minutes} minute{'s' if minutes > 1 else ''}"


def model_notice(deps: Deps, used: list[str]) -> str | None:
    """Tell the person when a backup model wrote (part of) the answer — and why."""
    if not deps.models:
        return None
    main = deps.models[0]
    backups = [m for m in dict.fromkeys(used) if m != main]
    if not backups:
        return None
    why = ("has used up its free daily limit" if deps.usage and deps.usage.resting_until(main)
           else "was unavailable")
    return f"{_short(main)} {why}, so this answer came from the backup model {' and '.join(map(_short, backups))}."


def friendly_error(exc: Exception, deps: Deps | None = None) -> str:
    """Pick a message that points the user in the right direction. Only a real rate limit says
    "rate-limited": the accuracy report counts those questions as "not run" instead of wrong."""
    if isinstance(exc, LLMOutputError):
        return "The AI gave a reply I couldn't use. Please try again, or try rephrasing your question."
    if isinstance(exc, SQLAlchemyError):
        return "The database is unavailable right now. Please try again shortly."
    if is_rate_limit(exc) and deps and deps.usage and deps.models:
        backs = [deps.usage.resting_until(m) for m in deps.models]
        if all(backs):  # every model is resting: say so, and when the first one is back
            soonest = min(backs) - deps.usage.clock()
            names = ", ".join(map(_short, deps.models))
            return (f"All {len(deps.models)} AI models ({names}) are rate-limited: they have used up their free daily allowance. "
                    f"The first one is back in about {_minutes(soonest)}.")
    if is_rate_limit(exc):
        rest = daily_limit_rest(exc)  # every model is out for the day: say when the main one is back
        if rest is not None:
            return ("The AI service is rate-limited right now: the free daily allowance is used up. "
                    f"Try again in about {_minutes(rest)}.")
        return "The AI service is rate-limited right now (free-tier limit). Please try again in a minute."
    if isinstance(exc, _transient_errors()):
        return "The AI service is unavailable right now. Please try again in a minute."
    return "Something went wrong while answering. The details are in the server log."


def _initial_state(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str) -> dict:
    """The starting notepad, including this person's recent turns (if conversation memory is on)."""
    history = []
    if deps.memory is not None:
        history = [{"question": t.question, "standalone": t.standalone, "answer": t.answer, "kind": t.kind}
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
    used: list[str] = []  # every AI model that answered a step of this question
    try:
        final = build_graph(deps).invoke(_initial_state(deps, question, role, patient_id, session_id),
                                         config={"configurable": {MODELS_USED_KEY: used}})
        result = _package(final).model_copy(update={"model_notice": model_notice(deps, used),
                                                  "models_used": list(dict.fromkeys(used))})
    except Exception as exc:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        _log_failure(exc)
        result = ChatResult(kind="error", answer=friendly_error(exc, deps))
        final = None
    _remember(deps, question, role, patient_id, session_id, result)
    _save_query(deps, final, result, role, patient_id)
    return result


def _log_failure(exc: Exception) -> None:
    """A rate limit is expected on the free tier: one warning line. Anything else: the full traceback."""
    if is_rate_limit(exc):
        log.warning("chat pipeline stopped: every AI model is rate-limited (%s)", str(exc).splitlines()[0][:160])
    else:
        log.exception("chat pipeline failed")


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
    used: list[str] = []  # every AI model that answered a step of this question
    try:
        stream = build_graph(deps).stream(_initial_state(deps, question, role, patient_id, session_id),
                                          config={"configurable": {MODELS_USED_KEY: used}},
                                          stream_mode=["tasks", "values"])
        for mode, chunk in stream:
            if mode == "values":
                final = chunk
            elif "input" in chunk and chunk.get("name") in REPORTED_STEPS:  # a step is starting
                step_input = chunk["input"] or {}
                if chunk["name"] == "contextualize" and not step_input.get("history"):
                    continue  # nothing to recall: the step does nothing, so don't announce it
                yield {"event": "progress", "data": _progress(chunk["name"], step_input)}
        result = _package(final).model_copy(update={"model_notice": model_notice(deps, used),
                                                  "models_used": list(dict.fromkeys(used))})
    except Exception as exc:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        _log_failure(exc)
        result = ChatResult(kind="error", answer=friendly_error(exc, deps))
        _remember(deps, question, role, patient_id, session_id, result)
        yield {"event": "error", "data": {"message": result.answer}}
        return
    _remember(deps, question, role, patient_id, session_id, result)
    _save_query(deps, final, result, role, patient_id)
    yield {"event": "final", "data": result.model_dump()}


OPTION_KINDS = ("clarification", "out_of_scope")


def _package(final: dict) -> ChatResult:
    """The pipeline's final notepad -> the tidy result the API returns."""
    return ChatResult(
        answer=final["answer"],
        kind=final["kind"],
        route=final["route"].kind if final.get("route") else None,
        standalone_question=final["question"] if final.get("original_question") else None,
        # One-click replies: a clarifying question's options, or example questions after "out of scope".
        options=final["route"].options if final.get("route") and final.get("kind") in OPTION_KINDS else [],
        option_questions=(final["route"].option_questions
                          if final.get("route") and final.get("kind") in OPTION_KINDS else {}),
        # One record per try, on its own database; shows what really ran (with any row filter added).
        sql=[SqlRecord(db=a.get("db") or final.get("db", "clinical"), query=a.get("executed") or a["sql"],
                       error=a["error"]) for a in final.get("attempts") or []],
        sources=final.get("sources") or [],
        table=final.get("result"),
        unverified_numbers=final.get("unverified_numbers") or [],
        documents=[DocumentRef(label=c.label, source_url=c.source_url, excerpt=c.text[:300])
                   for c in final.get("chunks") or []],
        timings=final.get("timings") or {},
        saved_query=_used_saved_sql(final),
    )


def _final_sql(final: dict) -> list[dict] | None:
    """Each plan step's SQL that worked (the AI's text, before any patient filter) — or None if a step has none."""
    attempts = final.get("attempts") or []
    out = []
    for i, _ in enumerate(final.get("plan") or []):
        ok = [a for a in attempts if a.get("step", 0) == i and not a.get("error")]
        if not ok:
            return None
        out.append(ok[-1])
    return out or None


def _used_saved_sql(final: dict) -> bool:
    steps = _final_sql(final) if final.get("saved_query") is not None else None
    return bool(steps) and all(a.get("saved") for a in steps)


def _save_query(deps: Deps, final: dict | None, result: ChatResult, role: str, patient_id: str | None) -> None:
    """Remember how a clean answer was found, so the same question runs the same SQL next time (saved_queries.py)."""
    if deps.saved_queries is None or not final or result.kind != "answer" or result.unverified_numbers:
        return
    route = final.get("route")
    if route is None or route.kind not in ("sql", "hybrid") or not worth_saving(final["question"]):
        return
    steps = _final_sql(final)
    if not steps or all(a.get("saved") for a in steps):
        return  # a step didn't run, or nothing changed since it was saved
    if role == "patient" and patient_id and any(patient_id in a["sql"] for a in steps):
        return  # never keep SQL that names this patient: it could be reused for another
    query = SavedQuery(route=route.model_copy(update={"options": [], "option_questions": {}}), plan=final["plan"],
                       link=final.get("link"), sql=[SavedSql(step=a.get("step", 0), db=a["db"], sql=a["sql"]) for a in steps],
                       standalone=final["question"] if final.get("original_question") else None,
                       question=final["question"])
    owner = patient_id if role == "patient" else None
    try:
        deps.saved_queries.save(role, final["question"], query, owner=owner)
        history = final.get("history") or []
        if final.get("original_question") and history:  # a follow-up: also under previous question + what was typed
            previous = history[-1].get("standalone") or history[-1]["question"]
            deps.saved_queries.save(role, follow_up_key(previous, final["original_question"]), query, owner=owner,
                                    comparable=False)
    except Exception:  # noqa: BLE001 — saving is a bonus; the answer is already done
        log.warning("couldn't save the query for reuse", exc_info=True)
