"""Step: ROUTE — the traffic cop.

Plain English: reads the question and decides what kind of question it is:
answerable from our databases ("sql", and which database), not something we can answer
("out_of_scope"), or not allowed for this user ("refuse", e.g. a patient asking about
other patients). The AI makes the call and replies in a fixed JSON format.
Two more kinds came with the drug-label library: "rag" (a question about medicines in general,
answered from FDA labels) and "hybrid" (records + labels: "side effects of MY medications").

Before asking the AI, one check is done by plain code: in patient mode, a question that names
ANOTHER patient from our records ("show me Miranda712 Jacobs452's medications") is refused
straight away. A smaller AI model once let such a question through; the database's privacy
filter still showed only the asker's own rows, but the answer then presented them as the other
person's. Code doesn't have off days.
"""

import re

from app.graph.deps import Deps
from app.graph.state import ChatState, RouteDecision
from app.graph.timing import timed
from app.llm.client import ask_json
from app.llm.prompts import route_system
from app.memory.saved_queries import (ASSUME_ASK, GO_AHEAD, NO, SIMILAR_ASK, SOMETHING_ELSE, YES,
                                      assumption_accepted, similar_ask_reply, with_assumptions)
from app.search.spelling import suggest_drug_spelling


def names_another_patient(question: str, patient_names: dict[str, str], self_id: str | None,
                          provider_names: list[str] = ()) -> bool:
    """True if the question mentions a different patient: by full name ("Miranda712 Jacobs452" or
    "Miranda Jacobs"), or by a single Synthea name token ("Miranda712") that no doctor also uses —
    Synthea reuses surnames like "Bosco882" for patients AND doctors (final review: 63 of 111 patients
    were wrongly refused when asking about their own doctor)."""
    q = " ".join(question.lower().split())
    own = set(patient_names.get(self_id or "", "").lower().split())
    doctor_tokens = {t for name in provider_names for t in name.lower().split()}
    for pid, name in patient_names.items():
        if pid == self_id:
            continue
        tokens = name.lower().split()
        full = [tokens, [t.rstrip("0123456789") for t in tokens]]
        if any(len(n) >= 2 and all(n) and re.search(rf"\b{re.escape(n[0])}\s+{re.escape(n[-1])}\b", q) for n in full):
            return True
        single = [t for t in tokens if any(c.isdigit() for c in t) and t not in own and t not in doctor_tokens]
        if any(re.search(rf"\b{re.escape(t)}\b", q) for t in single):
            return True
    return False


@timed("route")
def route(state: ChatState, deps: Deps) -> dict:
    # Check what the person typed AND the rewritten follow-up: a rewrite can drop Synthea's digits
    # ("and what about Bob3?" -> "What medications is Bob taking?") — final review, Plan 4.
    asked = [state["question"], state.get("original_question") or ""]
    if state["role"] == "patient" and any(names_another_patient(q, deps.patient_names, state.get("patient_id"),
                                                                deps.provider_names) for q in asked if q):
        return {"route": RouteDecision(kind="refuse", reason="names another patient (checked by code)")}
    saved = state.get("saved_query")
    if saved is None and deps.saved_queries is not None:
        saved = deps.saved_queries.get(state["role"], state["question"])
    if saved is not None:
        # Asked before and answered cleanly: same route, same plan, same SQL -> same numbers (saved_queries.py).
        return {"route": saved.route, "saved_query": saved}
    typed = state.get("original_question") or state["question"]
    if deps.saved_queries is not None and similar_ask_reply(state.get("history") or [], typed) != "no":
        owner = state.get("patient_id") if state["role"] == "patient" else None  # patients: only their own questions
        match = deps.saved_queries.similar(state["role"], state["question"], owner=owner)
        if match is not None and match.kind == "same":  # a very close rewording: same SQL, said how it was read
            return {"route": match.query.route, "saved_query": match.query, "question": match.question,
                    "original_question": typed}
        if match is not None:  # similar, but not sure: ask instead of assuming
            return {"route": RouteDecision(kind="clarify", reason=f"similar to a saved question ({match.score})",
                                           clarify_question=SIMILAR_ASK.format(match.question), options=[YES, NO],
                                           option_questions={YES: match.question, NO: typed})}
    decision = ask_json(deps.llm, route_system(state["role"]), state["question"], RouteDecision)
    if decision.kind == "clarify":  # keep only full questions for options actually offered
        decision = decision.model_copy(update={"option_questions": {
            o: q.strip() for o, q in decision.option_questions.items() if o in decision.options and q.strip()}})
    if (decision.kind in ("sql", "hybrid", "rag") and decision.assumptions
            and not assumption_accepted(state.get("history") or [], typed)):
        # The router would have to assume something the person didn't say: ask them instead of guessing.
        said = "; ".join(a.strip().rstrip(".") for a in decision.assumptions if a.strip())
        return {"route": RouteDecision(kind="clarify", reason=f"would have to assume: {said}",
                                       clarify_question=ASSUME_ASK.format(said), options=[GO_AHEAD, SOMETHING_ELSE],
                                       option_questions={GO_AHEAD: with_assumptions(typed, [said]),
                                                         SOMETHING_ELSE: ""})}
    if decision.kind == "sql" and not decision.databases:
        decision = decision.model_copy(update={"databases": ["clinical"]})
    if decision.kind == "hybrid":  # a person's medicines live in clinical_db; labels are looked up afterwards
        decision = decision.model_copy(update={"databases": ["clinical"]})
    if decision.kind in ("rag", "hybrid") and deps.store is not None:
        # A misspelled medicine ("metfromin"): ask "did you mean metformin?" instead of guessing. Checked on what
        # the person typed — a follow-up rewrite may already have quietly "fixed" it.
        typed = state.get("original_question") or state["question"]
        if (s := suggest_drug_spelling(typed, deps.store.drug_names(), correct=state["question"])):
            decision = RouteDecision(kind="clarify", reason=f"possible misspelling of a medicine: {s.word}",
                                     clarify_question=s.question, options=list(s.option_questions),
                                     option_questions=s.option_questions)
    return {"route": decision}
