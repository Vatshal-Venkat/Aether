"""Decision points between steps (LangGraph calls these "conditional edges").

Plain English: after checking or running a query we ask "what next?":
  * it failed and we still have tries left  -> go back and let the AI fix it;
  * it failed 3 times (counted per plan step) -> give up politely;
  * it worked (even with zero rows)         -> move on. An empty result is a real answer
    ("no records found"), not an error, so it never triggers a retry.
After a step finishes: another step to do -> round the loop again; otherwise -> merge.
"""

from typing import Literal

from app.graph.state import ChatState
from app.graph.steps import step_attempts


def _last_error(state: ChatState) -> str | None:
    attempts = step_attempts(state)
    return attempts[-1]["error"] if attempts else "no query"


def _retry_or_fail(state: ChatState, max_attempts: int) -> Literal["generate_sql", "fail"]:
    return "generate_sql" if len(step_attempts(state)) < max_attempts else "fail"


def after_validate(state: ChatState, max_attempts: int) -> Literal["row_filter", "generate_sql", "fail"]:
    return _retry_or_fail(state, max_attempts) if _last_error(state) else "row_filter"


def after_row_filter(state: ChatState, max_attempts: int) -> Literal["execute", "generate_sql", "fail"]:
    return _retry_or_fail(state, max_attempts) if _last_error(state) else "execute"


def after_execute(state: ChatState, max_attempts: int) -> Literal["next_step", "generate_sql", "fail"]:
    return _retry_or_fail(state, max_attempts) if _last_error(state) else "next_step"


def after_next_step(state: ChatState) -> Literal["inject_schema", "merge"]:
    """next_step already moved `step` on; it only clears `result` when another step should run."""
    plan = state.get("plan") or []
    return "inject_schema" if state.get("step", 0) < len(plan) and state.get("result") is None else "merge"
