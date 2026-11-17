"""Decision points between steps (LangGraph calls these "conditional edges").

Plain English: after checking or running a query we ask "what next?":
  * it failed and we still have tries left  -> go back and let the AI fix it;
  * it failed 3 times                       -> give up politely;
  * it worked (even with zero rows)         -> move on. An empty result is a real answer
    ("no records found"), not an error, so it never triggers a retry.
"""

from typing import Literal

from app.graph.state import ChatState


def _last_error(state: ChatState) -> str | None:
    attempts = state.get("attempts") or []
    return attempts[-1]["error"] if attempts else "no query"


def _retry_or_fail(state: ChatState, max_attempts: int) -> Literal["generate_sql", "fail"]:
    return "generate_sql" if len(state.get("attempts") or []) < max_attempts else "fail"


def after_validate(state: ChatState, max_attempts: int) -> Literal["execute", "generate_sql", "fail"]:
    return _retry_or_fail(state, max_attempts) if _last_error(state) else "execute"


def after_execute(state: ChatState, max_attempts: int) -> Literal["synthesize", "generate_sql", "fail"]:
    return _retry_or_fail(state, max_attempts) if _last_error(state) else "synthesize"
