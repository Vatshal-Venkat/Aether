"""Fixed replies that need no AI call: giving up, refusing, or "that's not something I can answer"."""

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed


@timed("refuse")
def refuse(state: ChatState, deps: Deps) -> dict:
    if state.get("role") == "patient":
        answer = "In patient mode I can only answer questions about your own records."
    else:
        answer = "I can't do that. I can only read and summarise the health records — never change or delete them."
    return {"kind": "refusal", "answer": answer}


@timed("out_of_scope")
def out_of_scope(state: ChatState, deps: Deps) -> dict:
    return {
        "kind": "out_of_scope",
        "answer": "I can only answer questions about the health records in this system — "
        "patients, visits, diagnoses, lab results, medications, procedures, vaccines, allergies, "
        "doctors, hospitals, insurers and insurance claims — plus FDA drug-label information "
        "about the medicines in those records.",
    }


@timed("fail")
def fail(state: ChatState, deps: Deps) -> dict:
    return {
        "kind": "error",
        "answer": "I couldn't build a working query for that after 3 tries. "
        "Try rephrasing, or ask something more specific.",
    }


@timed("clarify")
def clarify(state: ChatState, deps: Deps) -> dict:
    """Ask back instead of guessing ("Revenue of what — a hospital or an insurer?"); the website shows
    the router's suggested options as one-click replies."""
    question = state["route"].clarify_question.strip() or "Could you say a bit more about what you mean?"
    return {"kind": "clarification", "answer": question}
