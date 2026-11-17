"""Run one question through the pipeline and package the result for the API.

Plain English: takes a question plus "who is asking", runs the flowchart, and returns a
tidy result: the answer, what kind of answer it is, every SQL attempt (so you can see the
self-correction happen), the sources, the result table and how long each step took.
If the AI service is down or rate-limited, you get a friendly message instead of a crash.
"""

import logging

from pydantic import BaseModel

from app.config import Settings
from app.db.catalog import build_catalog
from app.db.engines import DbName, get_engine
from app.graph.build import build_graph
from app.graph.deps import Deps
from app.graph.state import AnswerKind, QueryResult
from app.llm.client import get_chat_model
from app.semantic.glossary import load_glossary

log = logging.getLogger(__name__)


class SqlRecord(BaseModel):
    db: DbName
    query: str
    error: str | None = None


class ChatResult(BaseModel):
    answer: str
    kind: AnswerKind
    sql: list[SqlRecord] = []
    sources: list[str] = []
    table: QueryResult | None = None
    unverified_numbers: list[str] = []
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
    )


def run_chat(deps: Deps, question: str, role: str, patient_id: str | None, session_id: str) -> ChatResult:
    state = {"question": question, "role": role, "patient_id": patient_id, "session_id": session_id,
             "attempts": [], "timings": {}}
    try:
        final = build_graph(deps).invoke(state)
    except Exception:  # noqa: BLE001 — the user gets a friendly message; details go to the log
        log.exception("chat pipeline failed")
        return ChatResult(
            kind="error",
            answer="The AI service is unavailable or rate-limited right now. Please try again in a minute.",
        )
    db = final.get("db", "clinical")
    return ChatResult(
        answer=final["answer"],
        kind=final["kind"],
        sql=[SqlRecord(db=db, query=a["sql"], error=a["error"]) for a in final.get("attempts") or []],
        sources=final.get("sources") or [],
        table=final.get("result"),
        unverified_numbers=final.get("unverified_numbers") or [],
        timings=final.get("timings") or {},
    )
