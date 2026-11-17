"""Step: VALIDATE — the safety inspector checks the AI's SQL before it runs.

Plain English: the latest query goes through the SQL safety checker (read-only? known
tables? no private columns? no tricks?). If it fails, the reason is written next to that
attempt so the AI can read it and try again. If it passes, the cleaned-up query (with a
row LIMIT added) becomes the one we will run.
"""

from app.graph.deps import Deps
from app.graph.state import ChatState
from app.graph.timing import timed
from app.safety.sql_validator import validate_sql

DIALECTS = {"clinical": "postgres", "billing": "mysql"}


@timed("validate")
def validate(state: ChatState, deps: Deps) -> dict:
    db = state["db"]
    attempts = [dict(a) for a in state["attempts"]]
    result = validate_sql(
        attempts[-1]["sql"],
        DIALECTS[db],
        allowed_tables=deps.catalog.allowed_tables(db),
        blocked_columns=set(deps.glossary.pii_columns),
        # +1 so execute can tell "exactly the cap" from "more rows exist" (truncated flag).
        default_limit=deps.settings.rows_stored_cap + 1,
    )
    if not result.ok:
        attempts[-1]["error"] = f"Rejected by safety check: {result.error}"
        return {"attempts": attempts, "final_sql": None}
    return {"attempts": attempts, "final_sql": result.sql}
