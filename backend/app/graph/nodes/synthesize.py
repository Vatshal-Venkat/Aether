"""Step: SYNTHESIZE — turn rows into a short, plain-English answer.

Plain English: the AI receives the question, the SQL that ran, the result rows (at most
ROWS_TO_LLM of them) and where they came from, and writes a brief answer using ONLY those
numbers, naming its sources. If the query found nothing, we don't ask the AI at all —
we simply say "No records found", so there is nothing to invent.
For drug questions the AI also gets the FDA label passages, fenced off as reference text, and
must cite them ("openFDA label: Lisinopril — Side effects").
When the AI sees only part of a long table, code adds the highest / lowest (and first / last) values over ALL rows
(app/safety/extremes.py): live, an AI shown 10 of 17 yearly rows called 2018's 382 visits "the peak" — 2021 had 502.
"""

import re

from app.db.engines import DB_LABEL
from app.graph.deps import Deps
from app.graph.state import ChatState, QueryResult
from app.graph.timing import timed
from app.llm.client import ask_text
from app.llm.prompts import RAG_RULES
from app.safety.extremes import extremes_note
from app.safety.row_meaning import distinct_note

SYSTEM = """You answer questions about healthcare data using ONLY the query results provided.
Rules:
- Use only numbers and facts that appear in the results. Never estimate, extrapolate or invent.
- Be brief: one to four sentences, or a short markdown list/table when listing several items.
- End with the sources in the form "Source: <database.table>, ...".
- Write every number as digits (4, not "four").
- If the results were truncated, say the list is partial.
- Do not show internal ID columns (long codes like 007a32fb-33a3-...) unless the user asked for IDs;
  show names, dates and descriptions instead.
- Money: a negative balance or amount owed is a credit (overpaid), not money owed — never list it as owing.
  If fewer rows qualify than the user asked for, say how many do.
- Rankings: rank by the measure the question asks about, in the order given. If rows are tied (the same
  value, especially at the end of a "top N" list), say that they are tied instead of implying an order.
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

EMPTY_REPLY = "I found the results but couldn't write a summary this time. The full table is attached below."
LONG_LIST = 15   # more rows than this: summarise instead of listing
LONG_LIST_SAMPLE = 10


TOP_N = re.compile(r"\b(?:top|first|best|highest|largest|biggest|lowest|bottom)\s+(\d{1,3})\b", re.IGNORECASE)


def tie_note(question: str, result: QueryResult) -> str | None:
    """The user asked for the top N but more rows came back because rows tie at the cut-off (the query keeps
    them on purpose, see app/db/ties.py): say so plainly, so the answer lists them all and calls them tied."""
    m = TOP_N.search(question)
    n = int(m.group(1)) if m else 0
    rows = result.rows
    if not n or len(rows) <= n:
        return None
    for c in range(len(result.columns) - 1, -1, -1):  # the measure is usually last (or the "ranking" column)
        value = rows[n - 1][c]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and rows[n][c] == value:
            first = next(i for i in range(n) if rows[i][c] == value) + 1
            last = max(i for i in range(len(rows)) if rows[i][c] == value) + 1
            shown = value if result.columns[c].lower() != "ranking" else f"rank {value}"
            return (f"The user asked for the top {n}, but {len(rows)} rows are shown because rows {first}-{last} are "
                    f"tied ({result.columns[c]} = {shown}). List every row and say clearly that rows {first}-{last} "
                    "are tied, instead of cutting the list or implying an order between them.")
    return None


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
    if result is not None and (len(result.rows) > shown or result.truncated) and (facts := extremes_note(result)):
        user += (f"{facts}\nYou see only {shown} of the rows: state any highest, lowest, peak or trend only from these "
                 "computed facts, never from the rows shown.\n\n")
    if result is not None and (rows_note := distinct_note(result)):  # "19 rows cover only 8 different patients"
        user += f"{rows_note}\n\n"
    if result is not None and (note := tie_note(state["question"], result)):
        user += f"Note: {note}\n\n"
    if result is not None and result.total_rows == 0 and chunks:
        # Final review: without this, "What is my amoxicillin used for?" from someone who never took it
        # could get "Your amoxicillin is used for…".
        user += ("Note: the database search found no matching records for this person — this medicine is not in "
                 "their records. Answer from the label only, and say plainly that it is not in their records.\n\n")
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
    answer = ask_text(deps.llm, system, user)
    if not answer.strip():  # live (2026-11-20): the AI's reply was empty — try once more
        answer = ask_text(deps.llm, system, user)
    return answer.strip() or EMPTY_REPLY


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
        # No rows — but if drug-label passages were found (the question named the medicine), they can
        # still answer it. Accuracy report (HY03): "No records found" while metformin's label was right there.
        if (result.total_rows == 0 or all_empty) and not state.get("chunks"):
            where = ", ".join(state.get("sources") or []) or "the database"
            return {"kind": "answer", "answer": f"No records found for that question (searched {where})."}
    elif not state.get("chunks"):
        return {"kind": "answer", "answer": NOTHING_IN_LABELS}
    return {"kind": "answer", "answer": draft_answer(state, deps)}
