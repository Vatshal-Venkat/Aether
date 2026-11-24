"""Step: VALIDATE — the safety inspector checks the AI's SQL before it runs.

Plain English: the latest query goes through the SQL safety checker (read-only? known
tables? no private columns? no tricks?). If it fails, the reason is written next to that
attempt so the AI can read it and try again. If it passes, the cleaned-up query (with a
row LIMIT added) becomes the one we will run.
"""

import re

from app.graph.deps import Deps
from app.graph.nodes.generate_sql import step1_measures
from app.graph.state import ChatState
from app.graph.timing import timed
from app.safety.sql_validator import validate_sql

DIALECTS = {"clinical": "postgres", "billing": "mysql"}
AGGREGATE = re.compile(r"\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(", re.IGNORECASE)


def lookup_problem(sql: str, measures: list[str], own_columns: set[str]) -> str | None:
    """Step 2 after a ranking may only look up names and details. Accuracy report 2026-11-23 (XD06): told so in
    words, the AI still re-computed "amount owed" from visit costs, or selected step 1's column (not in this
    database). Saying it in the error makes the retry fix it."""
    figures = ", ".join(measures)
    if AGGREGATE.search(sql):
        return (f"this step only looks up names and details: step 1 already worked out {figures}, and code keeps "
                "those figures. Remove COUNT/SUM/AVG/MIN/MAX and GROUP BY; select only descriptive columns.")
    foreign = [m for m in measures if m.lower() not in own_columns and re.search(rf"\b{re.escape(m)}\b", sql, re.IGNORECASE)]
    if foreign:
        return (f"{', '.join(foreign)} came from step 1 on the other database and is not a column here; code adds it. "
                "Select only this database's descriptive columns.")
    return None


RUNNING_BALANCE = re.compile(r"\bSUM\s*\(\s*(?:\w+\.)?outstanding\s*\)", re.IGNORECASE)
RUNNING_BALANCE_ERROR = ("claims_transactions.outstanding is a running balance repeated on every line item: summing it "
                         "counts the same money many times. For money still owed use claims.outstandingp (by the "
                         "patient) or claims.outstanding1 + claims.outstanding2 (by insurers).")


@timed("validate")
def validate(state: ChatState, deps: Deps) -> dict:
    db = state["db"]
    attempts = [dict(a) for a in state["attempts"]]
    # Accuracy report 2026-11-24 (XD02, XD07): the glossary says not to, the AI did it anyway (779,415.28 for 211.38).
    if RUNNING_BALANCE.search(attempts[-1]["sql"]):
        attempts[-1]["error"] = f"Rejected: {RUNNING_BALANCE_ERROR}"
        return {"attempts": attempts, "final_sql": None}
    result = validate_sql(
        attempts[-1]["sql"],
        DIALECTS[db],
        allowed_tables=deps.catalog.allowed_tables(db),
        blocked_columns=deps.glossary.blocked_columns(state["role"]),
        # +1 so execute can tell "exactly the cap" from "more rows exist" (truncated flag).
        default_limit=deps.settings.rows_stored_cap + 1,
    )
    if not result.ok:
        attempts[-1]["error"] = f"Rejected by safety check: {result.error}"
        return {"attempts": attempts, "final_sql": None}
    if (measures := step1_measures(state)):
        own = {c.name.lower() for table in deps.catalog.for_db(db) for c in table.columns}
        if (problem := lookup_problem(attempts[-1]["sql"], measures, own)):
            attempts[-1]["error"] = f"Rejected: {problem}"
            return {"attempts": attempts, "final_sql": None}
    return {"attempts": attempts, "final_sql": result.sql}
