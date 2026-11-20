"""Step: VERIFY NUMBERS — the fact-checker.

Plain English: every number in the drafted answer is checked against the query results.
If some don't match, the AI gets ONE more try, told exactly which numbers were wrong.
If it still fails, the answer is shown with a visible warning listing those numbers —
we never silently show an invented figure.

It also checks claims about the extremes: a number called the peak / highest / lowest must be that, over ALL the
rows (app/safety/extremes.py) — live, "a peak of 382 in 2018" passed the number check (382 is real) but 2021 had 502.
"""

from datetime import date

from app.graph.deps import Deps
from app.graph.nodes.synthesize import draft_answer
from app.graph.state import ChatState
from app.graph.timing import timed
from app.safety.extremes import wrong_extremes
from app.safety.number_check import find_unverified_numbers


def _unverified(answer: str, state: ChatState) -> list[str]:
    """Numbers must come from the result rows or from the drug-label passages the AI was shown."""
    result = state.get("result")
    rows = list(result.rows) if result else []
    rows += [[c.text] for c in state.get("chunks") or []]
    # Citation names can contain numbers ("openFDA label: Metformin Er 500 Mg"): they're sources, not claims.
    rows += [[s] for s in state.get("sources") or []]
    extra = {float(date.today().year), float(len(state.get("chunks") or []))}
    if result:
        extra |= {float(result.total_rows), float(len(result.rows))}
    return find_unverified_numbers(answer, rows, state["question"], extra)


def _problems(answer: str, state: ChatState) -> tuple[list[str], list[str]]:
    return _unverified(answer, state), wrong_extremes(answer, state.get("result"))


def _correction(bad: list[str], wrong: list[str]) -> str:
    parts = []
    if bad:
        parts.append(f"Your previous answer contained numbers not present in the results: {', '.join(bad)}. "
                     "Rewrite it using only numbers from the results.")
    if wrong:
        parts.append(f"Your previous answer called a value the highest or lowest when it isn't: {'; '.join(wrong)}. "
                     "Rewrite it with the correct highest and lowest values over all the rows.")
    return " ".join(parts)


@timed("verify_numbers")
def verify_numbers(state: ChatState, deps: Deps) -> dict:
    answer = state["answer"]
    bad, wrong = _problems(answer, state)
    if not bad and not wrong:
        return {"unverified_numbers": []}
    answer = draft_answer(state, deps, correction=_correction(bad, wrong))
    bad, wrong = _problems(answer, state)
    if bad:
        answer += f"\n\n⚠ Some numbers in this answer could not be matched to the query results: {', '.join(bad)}"
    return {"answer": answer, "unverified_numbers": bad + wrong}
