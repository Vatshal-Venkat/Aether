"""Small helpers: which plan step are we on, and which tries belong to it."""

from app.graph.state import ChatState, PlanStep


def current_step(state: ChatState) -> PlanStep:
    plan = state.get("plan")
    if plan:
        return plan[state.get("step", 0)]
    route = state.get("route")
    db = route.databases[0] if route and route.databases else "clinical"
    return PlanStep(db=db, goal=state["question"])


def step_attempts(state: ChatState) -> list[dict]:
    step = state.get("step", 0)
    return [a for a in state.get("attempts") or [] if a.get("step", 0) == step]


def is_multi_step(state: ChatState) -> bool:
    return len(state.get("plan") or []) > 1
