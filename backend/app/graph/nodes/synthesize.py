"""Step: SYNTHESIZE — turn rows into a short, plain-English answer.

Plain English: the AI receives the question, the SQL that ran, the result rows (at most
ROWS_TO_LLM of them) and where they came from, and writes a brief answer using ONLY those
numbers, naming its sources. If the query found nothing, we don't ask the AI at all —
we simply say "No records found", so there is nothing to invent.
"""

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed
from app.llm.client import ask_text

SYSTEM = """You answer questions about healthcare data using ONLY the query results provided.
Rules:
- Use only numbers and facts that appear in the results. Never estimate, extrapolate or invent.
- Be brief: one to four sentences, or a short markdown list/table when listing several items.
- End with the sources in the form "Source: <database.table>, ...".
- If the results were truncated, say the list is partial.
- Do not show internal ID columns (long codes like 007a32fb-33a3-...) unless the user asked for IDs;
  show names, dates and descriptions instead.
- Do not give medical advice; describe the data."""


def _results_table(state: ChatState, limit: int) -> str:
    result = state["result"]
    lines = [" | ".join(result.columns)]
    lines += [" | ".join("" if v is None else str(v) for v in row) for row in result.rows[:limit]]
    return "\n".join(lines)


def draft_answer(state: ChatState, deps: Deps, correction: str | None = None) -> str:
    result = state["result"]
    shown = min(len(result.rows), deps.settings.rows_to_llm)
    user = (
        f"Question: {state['question']}\n\n"
        f"SQL that ran:\n{state.get('final_sql')}\n\n"
        f"Results ({result.total_rows} rows{', TRUNCATED' if result.truncated else ''}; showing {shown}):\n"
        f"{_results_table(state, deps.settings.rows_to_llm)}\n\n"
        f"Sources: {', '.join(state.get('sources') or [])}"
    )
    if correction:
        user += f"\n\n{correction}"
    return ask_text(deps.llm, SYSTEM, user)


@timed("synthesize")
def synthesize(state: ChatState, deps: Deps) -> dict:
    result = state["result"]
    all_empty = all(v is None for row in result.rows for v in row)  # e.g. max(date) over nothing -> [[None]]
    if result.total_rows == 0 or all_empty:
        where = ", ".join(state.get("sources") or []) or "the database"
        return {"kind": "answer", "answer": f"No records found for that question (searched {where})."}
    return {"kind": "answer", "answer": draft_answer(state, deps)}
