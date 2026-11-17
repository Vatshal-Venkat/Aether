"""Step: GENERATE SQL — the AI writes the database query.

Plain English: the AI gets the question, the relevant tables, the glossary hints, and
strict rules (read-only, no private columns...). If a previous attempt failed, it also
sees its own failed query and the exact error, so it can correct itself — that is the
"self-correction" loop. We then cut the SQL out of the AI's reply.
"""

import re

from app.graph.deps import Deps
from app.graph.state import ChatState
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


@timed("generate_sql")
def generate_sql(state: ChatState, deps: Deps) -> dict:
    db = state.get("db") or (state["route"].databases[0] if state.get("route") and state["route"].databases else "clinical")
    attempts = list(state.get("attempts") or [])
    reply = ask_text(
        deps.llm,
        sql_system(DIALECT_NAMES[db], state["role"]),
        sql_user(state["question"], state["schema_text"], attempts),
    )
    attempts.append({"sql": extract_sql(reply), "error": None})
    return {"attempts": attempts, "db": db}
