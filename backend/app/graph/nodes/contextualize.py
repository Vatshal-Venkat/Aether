"""Step: CONTEXTUALIZE — turn a follow-up into a full question.

Plain English: "How many of them are female?" only makes sense after "How many patients have
diabetes?". If this conversation has earlier turns, the AI rewrites the new message into a question
that stands on its own ("How many patients with diabetes are female?"), and every later step works
on that. The website shows it as "Understood as: …", so you can see how Aether read you.

A follow-up asked before after the same question ("show their names" after "how many patients have diabetes?")
reuses the saved rewrite and SQL (app/memory/saved_queries.py), so it always reads — and answers — the same way.

A first question has no history, so this step does nothing and costs no AI call.
"""

from pydantic import BaseModel

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed
from app.llm.client import ask_json
from app.llm.prompts import CONTEXTUALIZE_SYSTEM, contextualize_user
from app.memory.saved_queries import assumption_accepted, follow_up_key, similar_ask_reply


class Standalone(BaseModel):
    standalone: str


@timed("contextualize")
def contextualize(state: ChatState, deps: Deps) -> dict:
    history = state.get("history") or []
    if not history:
        return {}
    typed = state["question"]
    if similar_ask_reply(history, typed) or assumption_accepted(history, typed):
        return {}  # a click on "Do you mean ...?" or "Yes, go ahead": already a full question
    if deps.saved_queries is not None:
        previous = history[-1].get("standalone") or history[-1]["question"]
        saved = deps.saved_queries.get(state["role"], follow_up_key(previous, typed))
        if saved is not None and saved.standalone:  # this follow-up after this question was answered before
            return {"question": saved.standalone, "original_question": typed, "saved_query": saved}
    context_llm = deps.fast_llm or deps.llm
    rewritten = ask_json(context_llm, CONTEXTUALIZE_SYSTEM, contextualize_user(history, typed), Standalone).standalone.strip()
    if not rewritten or rewritten == typed:
        return {}
    return {"question": rewritten, "original_question": typed}
