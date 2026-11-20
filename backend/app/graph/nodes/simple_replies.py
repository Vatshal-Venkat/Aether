"""Replies that end the conversation turn early: giving up, refusing, "that's not something I can answer",
or asking back.

When Aether doesn't understand, it should help the person ask again, not just stop:
  * clarify: the router's question plus one-click options; each option carries the full question it stands for
    ("Insurers" -> "Which insurance company has the highest revenue?"), so a click asks exactly that;
  * fail (3 tries at a query didn't work): one extra AI call suggests 2-3 close questions the data CAN answer, shown
    as one-click options ("Did you mean one of these?"). If that call fails or finds nothing, the plain message stays;
  * out_of_scope: a fixed reply (no AI call) plus three example questions to click.
"""

import logging

from pydantic import BaseModel

from app.graph.deps import Deps
from app.graph.nodes.route import names_another_patient
from app.graph.state import ChatState, RouteDecision
from app.graph.steps import step_attempts
from app.graph.timing import timed
from app.llm.client import ask_json
from app.llm.prompts import suggest_system, suggest_user

log = logging.getLogger(__name__)

FAIL_MESSAGE = "I couldn't build a working query for that after 3 tries. Try rephrasing, or ask something more specific."
NONE_OF_THESE = "None of these"
MAX_SUGGESTIONS = 3
EXAMPLES = {
    "clinician": ["How many patients are there?", "What are the most common diagnoses?",
                  "Which insurance company has the most customers?"],
    "patient": ["What medications am I taking?", "When was my last visit?", "What are the side effects of my medications?"],
}


class Suggestions(BaseModel):
    suggestions: list[str] = []


def _with_options(state: ChatState, question: str, options: list[str], option_questions: dict[str, str]) -> RouteDecision:
    route = state.get("route") or RouteDecision(kind="sql")
    return route.model_copy(update={"clarify_question": question, "options": options, "option_questions": option_questions})


@timed("refuse")
def refuse(state: ChatState, deps: Deps) -> dict:
    if state.get("role") == "patient":
        answer = "In patient mode I can only answer questions about your own records."
    else:
        answer = "I can't do that. I can only read and summarise the health records — never change or delete them."
    return {"kind": "refusal", "answer": answer}


@timed("out_of_scope")
def out_of_scope(state: ChatState, deps: Deps) -> dict:
    answer = ("I can only answer questions about the health records in this system — "
              "patients, visits, diagnoses, lab results, medications, procedures, vaccines, allergies, "
              "doctors, hospitals, insurers and insurance claims — plus FDA drug-label information "
              "about the medicines in those records. For example:")
    examples = EXAMPLES["patient" if state.get("role") == "patient" else "clinician"]
    return {"kind": "out_of_scope", "answer": answer,
            "route": _with_options(state, answer, examples, {e: e for e in examples})}


def _suggestions(state: ChatState, deps: Deps) -> list[str]:
    """2-3 close questions the data can answer — or [] if the AI can't help (any problem: keep the plain message)."""
    question, role = state.get("question", ""), state.get("role", "clinician")
    errors = [a.get("error") or "" for a in step_attempts(state)]
    try:
        got = ask_json(deps.llm, suggest_system(role), suggest_user(question, errors), Suggestions).suggestions
    except Exception:  # noqa: BLE001 — suggestions are a bonus; the plain "couldn't" message still works
        log.warning("couldn't get suggested questions after a failed query", exc_info=True)
        return []
    seen = {question.strip().lower()}
    clean = []
    for s in (s.strip() for s in got):
        if not s or s.lower() in seen:
            continue
        if role == "patient" and names_another_patient(s, deps.patient_names, state.get("patient_id"), deps.provider_names):
            continue  # never show another patient's name, even as a suggestion
        seen.add(s.lower())
        clean.append(s)
    return clean[:MAX_SUGGESTIONS]


@timed("fail")
def fail(state: ChatState, deps: Deps) -> dict:
    suggestions = _suggestions(state, deps)
    if not suggestions:
        return {"kind": "error", "answer": FAIL_MESSAGE}
    answer = "I couldn't work out a query for that. Did you mean one of these?"
    options = [*suggestions, NONE_OF_THESE]
    return {"kind": "clarification", "answer": answer,
            "route": _with_options(state, answer, options, {**{s: s for s in suggestions}, NONE_OF_THESE: ""})}


@timed("clarify")
def clarify(state: ChatState, deps: Deps) -> dict:
    """Ask back instead of guessing ("Revenue of what — a hospital or an insurer?"); the website shows
    the router's suggested options as one-click replies."""
    question = state["route"].clarify_question.strip() or "Could you say a bit more about what you mean?"
    return {"kind": "clarification", "answer": question}
