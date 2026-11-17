"""Step: ROUTE — the traffic cop.

Plain English: reads the question and decides what kind of question it is:
answerable from our databases ("sql", and which database), not something we can answer
("out_of_scope"), or not allowed for this user ("refuse", e.g. a patient asking about
other patients). The AI makes the call and replies in a fixed JSON format.
"""

from app.graph.deps import Deps
from app.graph.state import ChatState, RouteDecision
from app.graph.timing import timed
from app.llm.client import ask_json
from app.llm.prompts import route_system


@timed("route")
def route(state: ChatState, deps: Deps) -> dict:
    decision = ask_json(deps.llm, route_system(state["role"]), state["question"], RouteDecision)
    if decision.kind == "sql" and decision.databases != ["clinical"]:
        # Plan 1 only queries clinical_db; billing_db querying arrives in Plan 2.
        decision = decision.model_copy(update={
            "databases": ["clinical"],
            "reason": f"{decision.reason} (billing_db not yet connected; using clinical_db)",
        })
    return {"route": decision}
