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


class SqlAttempt(TypedDict):
    sql: str
    error: str | None


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]  # JSON-safe values only
    total_rows: int
    truncated: bool


def merge_dicts(a: dict, b: dict) -> dict:
    """Each step adds its own timing without erasing the others'."""
    return {**(a or {}), **(b or {})}


class ChatState(TypedDict, total=False):
    question: str
    role: Literal["clinician", "patient"]
    patient_id: str | None
    session_id: str
    route: RouteDecision
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
