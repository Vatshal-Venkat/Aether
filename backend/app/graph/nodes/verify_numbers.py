"""Step: VERIFY NUMBERS — the fact-checker.

Plain English: every number in the drafted answer is checked against the query results.
If some don't match, the AI gets ONE more try, told exactly which numbers were wrong.
If it still fails, the answer is shown with a visible warning listing those numbers —
we never silently show an invented figure.
"""

from datetime import date

from app.graph.deps import Deps
from app.graph.nodes.synthesize import draft_answer
from app.graph.state import ChatState
from app.graph.timing import timed
from app.safety.number_check import find_unverified_numbers


def _unverified(answer: str, state: ChatState) -> list[str]:
    """Numbers must come from the result rows or from the drug-label passages the AI was shown."""
    result = state.get("result")
    rows = list(result.rows) if result else []
    rows += [[c.text] for c in state.get("chunks") or []]
    extra = {float(date.today().year), float(len(state.get("chunks") or []))}
    if result:
        extra |= {float(result.total_rows), float(len(result.rows))}
    return find_unverified_numbers(answer, rows, state["question"], extra)


@timed("verify_numbers")
def verify_numbers(state: ChatState, deps: Deps) -> dict:
    answer = state["answer"]
    bad = _unverified(answer, state)
    if not bad:
        return {"unverified_numbers": []}
    answer = draft_answer(
        state, deps,
        correction=f"Your previous answer contained numbers not present in the results: {', '.join(bad)}. "
        "Rewrite it using only numbers from the results.",
    )
    bad = _unverified(answer, state)
    if bad:
        answer += f"\n\n⚠ Some numbers in this answer could not be matched to the query results: {', '.join(bad)}"
    return {"answer": answer, "unverified_numbers": bad}
