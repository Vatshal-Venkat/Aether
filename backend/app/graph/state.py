"""The shared notepad passed between pipeline steps.

Plain English: LangGraph runs our steps one after another. Each step reads this notepad
(the "state"), does its job, and writes a few new lines on it — e.g. the router writes
which database to use, the SQL writer adds its query, the executor adds the rows.
"""

from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel

from app.db.engines import DbName

RouteKind = Literal["sql", "out_of_scope", "refuse"]
AnswerKind = Literal["answer", "refusal", "out_of_scope", "error"]


class RouteDecision(BaseModel):
    kind: RouteKind
    databases: list[DbName] = []
    reason: str = ""


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
    question: str
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
    timings: Annotated[dict[str, float], merge_dicts]
