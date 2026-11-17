"""Step: SYNTHESIZE — turn rows into a short, plain-English answer.

Plain English: the AI receives the question, the SQL that ran, the result rows (at most
ROWS_TO_LLM of them) and where they came from, and writes a brief answer using ONLY those
numbers, naming its sources. If the query found nothing, we don't ask the AI at all —
we simply say "No records found", so there is nothing to invent.
For drug questions the AI also gets the FDA label passages, fenced off as reference text, and
must cite them ("openFDA label: Lisinopril — Side effects").
"""

from app.db.engines import DB_LABEL
from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed
from app.llm.client import ask_text
from app.llm.prompts import RAG_RULES

SYSTEM = """You answer questions about healthcare data using ONLY the query results provided.
Rules:
- Use only numbers and facts that appear in the results. Never estimate, extrapolate or invent.
- Be brief: one to four sentences, or a short markdown list/table when listing several items.
- End with the sources in the form "Source: <database.table>, ...".
- Write every number as digits (4, not "four").
- If the results were truncated, say the list is partial.
- Do not show internal ID columns (long codes like 007a32fb-33a3-...) unless the user asked for IDs;
  show names, dates and descriptions instead.
- Do not give medical advice; describe the data."""

# Live test: a router miss let a patient ask about someone else; the database (correctly) returned only
# her own rows, which the answer then presented as if they were the other person's.
PATIENT_RULES = """
- PATIENT MODE: the results always contain only the current patient's own records. If the question is
  about someone else (another named person, other patients), do not present these rows as theirs: say you can
  only show the patient their own records."""

NO_INDEX ="Drug information isn't loaded yet. Run: python -m scripts.build_drug_index"
UNKNOWN_DRUG = ("I don't have the FDA label for that medicine in this library — it only covers the medications "
                "that appear in our patient records.")
NOTHING_IN_LABELS = "I couldn't find anything about that in the FDA drug labels in this library."

LONG_LIST = 15   # more rows than this: summarise instead of listing
LONG_LIST_SAMPLE = 10


def _results_table(state: ChatState, limit: int) -> str:
    result = state["result"]
    lines = [" | ".join(result.columns)]
    lines += [" | ".join("" if v is None else str(v) for v in row) for row in result.rows[:limit]]
    return "\n".join(lines)


def _sql_that_ran(state: ChatState) -> str:
    """Every step's query, labelled with its database (two steps for a two-database question)."""
    steps = state.get("step_results") or []
    if not steps:
        return str(state.get("final_sql"))
    return "\n".join(f"-- step {i + 1} on {DB_LABEL[s.db]}:\n{s.sql}" for i, s in enumerate(steps))


def _excerpts(state: ChatState) -> str:
    """Label passages, clearly fenced off so the AI treats them as reference text, not instructions."""
    parts = [f"[{i}] {c.label}\n{c.text}" for i, c in enumerate(state.get("chunks") or [], 1)]
    return "<<<EXCERPTS\n" + "\n\n".join(parts) + "\nEXCERPTS>>>"


def draft_answer(state: ChatState, deps: Deps, correction: str | None = None) -> str:
    result = state.get("result")
    chunks = state.get("chunks") or []
    user = f"Question: {state['question']}\n\n"
    long_list = False
    if result is not None:
        long_list = result.total_rows > LONG_LIST
        limit = LONG_LIST_SAMPLE if long_list else deps.settings.rows_to_llm
        shown = min(len(result.rows), limit)
        user += (
            f"SQL that ran:\n{_sql_that_ran(state)}\n\n"
            f"Results ({result.total_rows} rows{', TRUNCATED' if result.truncated else ''}; showing {shown}):\n"
            f"{_results_table(state, limit)}\n\n"
        )
    if state.get("rag_note"):  # also when nothing was found: "no Boxed warning section for X" is an answer
        user += f"What was checked in the drug labels: {state['rag_note']}\n\n"
    if chunks:
        user += f"Drug-label excerpts:\n{_excerpts(state)}\n\n"
    user += f"Sources: {', '.join(state.get('sources') or [])}"
    if long_list:
        user += (
            f"\n\nThere are {result.total_rows}{'+' if result.truncated else ''} rows: do not list them all. "
            "Summarise in 1-3 sentences (you may mention a few examples) and say the full table is attached."
        )
    if correction:
        user += f"\n\n{correction}"
    system = SYSTEM + (PATIENT_RULES if state.get("role") == "patient" else "") + (RAG_RULES if chunks else "")
    return ask_text(deps.llm, system, user)


@timed("synthesize")
def synthesize(state: ChatState, deps: Deps) -> dict:
    problem = state.get("rag_problem")
    if problem == "no_index":
        return {"kind": "answer", "answer": NO_INDEX}
    if problem == "unknown_drug":
        return {"kind": "answer", "answer": UNKNOWN_DRUG}
    if problem == "missing_section":
        return {"kind": "answer", "answer": state["rag_message"]}
    result = state.get("result")
    if result is not None:  # a database query ran (sql or hybrid)
        all_empty = all(v is None for row in result.rows for v in row)  # e.g. max(date) over nothing -> [[None]]
        if result.total_rows == 0 or all_empty:
            where = ", ".join(state.get("sources") or []) or "the database"
            return {"kind": "answer", "answer": f"No records found for that question (searched {where})."}
    elif not state.get("chunks"):
        return {"kind": "answer", "answer": NOTHING_IN_LABELS}
    return {"kind": "answer", "answer": draft_answer(state, deps)}
