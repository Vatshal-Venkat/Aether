"""Step: CONTEXTUALIZE — turn a follow-up into a full question.

Plain English: "How many of them are female?" only makes sense after "How many patients have
diabetes?". If this conversation has earlier turns, the AI rewrites the new message into a question
that stands on its own ("How many patients with diabetes are female?"), and every later step works
on that. The website shows it as "Understood as: …", so you can see how Aether read you.

A first question has no history, so this step does nothing and costs no AI call.
"""

from pydantic import BaseModel

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed
from app.llm.client import ask_json
from app.llm.prompts import CONTEXTUALIZE_SYSTEM, contextualize_user


class Standalone(BaseModel):
    standalone: str


@timed("contextualize")
def contextualize(state: ChatState, deps: Deps) -> dict:
    history = state.get("history") or []
    if not history:
        return {}
    typed = state["question"]
    rewritten = ask_json(deps.llm, CONTEXTUALIZE_SYSTEM, contextualize_user(history, typed), Standalone).standalone.strip()
    if not rewritten or rewritten == typed:
        return {}
    return {"question": rewritten, "original_question": typed}
