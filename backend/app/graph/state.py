"""The shared notepad passed between pipeline steps.

Plain English: LangGraph runs our steps one after another. Each step reads this notepad
(the "state"), does its job, and writes a few new lines on it — e.g. the router writes
which database to use, the SQL writer adds its query, the executor adds the rows.
"""

from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel

from app.db.engines import DbName
from app.rag.store import Chunk

RouteKind = Literal["sql", "rag", "hybrid", "clarify", "out_of_scope", "refuse"]
AnswerKind = Literal["answer", "clarification", "refusal", "out_of_scope", "error"]


class RouteDecision(BaseModel):
    kind: RouteKind
    databases: list[DbName] = []
    reason: str = ""
    drugs: list[str] = []  # medicine names the router saw in the question (for drug-label lookups)
    clarify_question: str = ""  # kind "clarify": the short question to ask back
    options: list[str] = []     # kind "clarify": 2-4 likely answers the person can click


class SqlAttempt(TypedDict, total=False):
    step: int              # which plan step this try belongs to (0 or 1)
    db: DbName
    sql: str               # what the AI wrote
    executed: str | None   # what actually ran, if code added a row filter
    error: str | None


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]  # JSON-safe values only
    total_rows: int
    truncated: bool
    result_id: str | None = None  # ticket for fetching further pages (GET /api/results/{id})


class PlanStep(BaseModel):
    """One sub-question, answered from one database."""
    db: DbName
    goal: str


class QueryPlan(BaseModel):
    """What the AI proposes for a two-database question (checked by plan.normalize_plan)."""
    steps: list[PlanStep]
    link: str | None = None  # one of glossary.links, e.g. "encounters.provider = providers.id"


class Link(BaseModel):
    """How step 1's rows connect to step 2's: from = step 1's side, to = step 2's side."""
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class StepResult(BaseModel):
    db: DbName
    sql: str
    result: QueryResult
    sources: list[str]


def merge_dicts(a: dict, b: dict) -> dict:
    """Each step adds its own timing without erasing the others'. A step that runs more than
    once (a retry, or once per plan step) reports its total time."""
    merged = dict(a or {})
    for key, value in (b or {}).items():
        merged[key] = merged.get(key, 0.0) + value
    return merged


class ChatState(TypedDict, total=False):
    question: str                  # the standalone question (a follow-up is rewritten first)
    original_question: str         # what the person actually typed, when it was rewritten
    history: list[dict]            # recent turns of this conversation: question, answer, kind
    role: Literal["clinician", "patient"]
    patient_id: str | None
    session_id: str
    route: RouteDecision
    plan: list[PlanStep]
    link: Link | None
    step: int                      # index of the plan step being worked on
    step_results: list[StepResult]
    schema_text: str
    attempts: list[SqlAttempt]
    final_sql: str | None
    db: DbName
    result: QueryResult | None
    answer: str
    kind: AnswerKind
    sources: list[str]
    unverified_numbers: list[str]
    chunks: list[Chunk]            # drug-label passages found by retrieve
    rag_problem: str | None        # "no_index" | "unknown_drug" | "missing_section" | None
    rag_message: str               # the fixed answer for "missing_section"
    rag_note: str                  # what retrieve checked (medicines, section, gaps) — shown to the AI
    timings: Annotated[dict[str, float], merge_dicts]
