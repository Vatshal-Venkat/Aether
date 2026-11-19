"""Step: GENERATE SQL — the AI writes the database query.

Plain English: the AI gets the question, the relevant tables, the glossary hints, and
strict rules (read-only, no private columns...). If a previous attempt failed, it also
sees its own failed query and the exact error, so it can correct itself — that is the
"self-correction" loop. We then cut the SQL out of the AI's reply.

In a two-step plan the AI writes one query per step, and is told how the steps connect:
step 1 must output the linking column (e.g. encounters.provider); in step 2, code will keep
only the rows matching step 1's values, so the AI must not filter on them itself.
"""

import re

from app.db.engines import DB_LABEL
from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.steps import current_step, is_multi_step, step_attempts
from app.graph.timing import timed
from app.llm.client import ask_text
from app.llm.prompts import sql_system, sql_user

DIALECT_NAMES = {"clinical": "PostgreSQL", "billing": "MySQL"}


def extract_sql(text: str) -> str:
    """Pull the SQL out of an AI reply: a ``` block if present, else from the first SELECT/WITH."""
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    sql = fenced.group(1) if fenced else text
    if not fenced:
        start = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
        sql = sql[start.start():] if start else sql
    return sql.strip().rstrip(";").strip()


def link_notes(state: ChatState) -> list[str]:
    """What the AI must know about how this step connects to the other one."""
    link = state.get("link")
    if not link:
        return []
    if state.get("step", 0) == 0:
        other = DB_LABEL[state["plan"][1].db]
        return [f"Include the column {link.from_table}.{link.from_column} in the output, unaliased: "
                f"the next step uses it to look up {link.to_table} in {other}."]
    previous = state["step_results"][0].result
    n = len({str(r[i]) for r in previous.rows for i, c in enumerate(previous.columns)
             if c.lower() == link.from_column.lower() and r[i] is not None})
    notes = [f"Code will automatically keep only {link.to_table} rows whose {link.to_column} is one of the "
             f"{n} values found in step 1. Do not filter on {link.to_column} yourself. Step 1 already applied "
             "the question's conditions (which patients, doctors, diagnoses...): do not repeat them here — every "
             f"{link.to_table} row you will see already belongs to the question. Include "
             f"{link.to_table}.{link.to_column} unaliased if you return one row per item; for an overall "
             "total you may aggregate."]
    # Step 1 already produced the figures (a "rank, then look up names" plan): step 2 is only a lookup.
    # Live (2026-11-19): asked who owes the most, step 2 invented "amount_owed = expenses - coverage" and the
    # answer ranked by it instead of step 1's real balances.
    measures = [c for c in previous.columns if c.lower() != link.from_column.lower()]
    if measures:
        notes.append(f"Step 1 already worked out: {', '.join(measures)} — those figures and their order are kept "
                     "by code. This step is a plain lookup of descriptive details (names, descriptions, dates) for "
                     f"those {n} rows. Do not compute any amount, count or ranking, and use no ORDER BY or LIMIT.")
    return notes


def hybrid_notes(state: ChatState) -> list[str]:
    """A hybrid question: the SQL only finds the records; drug-label facts are added afterwards."""
    route = state.get("route")
    if not route or route.kind != "hybrid":
        return []
    return ["This query only needs to find the records the question is about (e.g. the medication "
            "descriptions). Side effects, warnings and other drug information are NOT in the database: they "
            "come from FDA labels, added afterwards. Do not filter on it — return the records, and code will "
            "check the labels."]


HYBRID_STEP = ("list the records the question is about (e.g. the medications, with their descriptions), "
               "ignoring the drug-information part of the question")


@timed("generate_sql")
def generate_sql(state: ChatState, deps: Deps) -> dict:
    step = current_step(state)
    db = step.db
    route = state.get("route")
    if route and route.kind == "hybrid":
        # Live test: given the bare question "...which have a boxed warning?", the SQL writer filtered on the
        # warning (AND false) and returned nothing. So the database part is spelled out as this step's task.
        question = f"Overall question: {state['question']}\nThis step: {HYBRID_STEP}"
    elif is_multi_step(state):
        question = f"Overall question: {state['question']}\nThis step: {step.goal}"
    else:
        question = state["question"]
    attempts = list(state.get("attempts") or [])
    reply = ask_text(
        deps.llm,
        sql_system(DIALECT_NAMES[db], state["role"]),
        sql_user(question, state["schema_text"], step_attempts(state), link_notes(state) + hybrid_notes(state)),
    )
    attempts.append({"step": state.get("step", 0), "db": db, "sql": extract_sql(reply), "executed": None, "error": None})
    return {"attempts": attempts, "db": db}
