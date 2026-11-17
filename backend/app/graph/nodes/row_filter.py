"""Step: ROW FILTER — code adds "only these rows" to the approved query, just before it runs.

Plain English: two situations need it.
  1. Patient mode on MySQL (billing_db). MySQL has no built-in privacy filter, so every
     mention of a patient table (claims, claims_transactions, payer_transitions) is swapped for
     "only this patient's rows". PostgreSQL does the same job itself with row-level security.
  2. Step 2 of a two-database plan. Step 1 found some ids (e.g. the busiest doctor's id);
     step 2 must look only at those (e.g. providers whose id is one of them). Code carries the
     ids across — the AI never copies them, so it can't get them wrong or slip anything in.
The rewritten query (what really runs) is kept on the attempt so you can see it.
"""

from app.data.synthea import PATIENT_COLUMN, TABLE_SPLIT
from app.db.engines import DB_LABEL
from app.graph.deps import Deps
from app.graph.nodes.validate import DIALECTS
from app.graph.state import ChatState
from app.graph.timing import timed
from app.safety.row_filter import RowFilter, restrict_tables
from app.safety.sql_validator import tables_in

BILLING_PATIENT_TABLES = {t: PATIENT_COLUMN[t] for t, db in TABLE_SPLIT.items() if db == "billing" and t in PATIENT_COLUMN}


def _link_values(state: ChatState) -> list[str]:
    link = state["link"]
    previous = state["step_results"][0].result
    idx = [i for i, c in enumerate(previous.columns) if c.lower() == link.from_column.lower()]
    return list(dict.fromkeys(str(r[idx[0]]) for r in previous.rows if r[idx[0]] is not None)) if idx else []


@timed("row_filter")
def row_filter(state: ChatState, deps: Deps) -> dict:
    db = state["db"]
    attempts = [dict(a) for a in state["attempts"]]
    sql = state["final_sql"]
    filters: list[RowFilter] = []
    if state["role"] == "patient" and db == "billing":
        filters += [RowFilter(t, col, [state["patient_id"]]) for t, col in BILLING_PATIENT_TABLES.items()]
    link = state.get("link")
    if link and state.get("step", 0) == 1:
        if link.to_table not in tables_in(sql, DIALECTS[db]):
            attempts[-1]["error"] = (f"Use the table {link.to_table} in this query: only its rows matching step 1 "
                                     f"are kept (by {link.to_column}).")
            return {"attempts": attempts, "final_sql": None}
        filters.append(RowFilter(link.to_table, link.to_column, _link_values(state)))
    if not filters:
        return {"attempts": attempts}
    try:
        rewritten = restrict_tables(sql, DIALECTS[db], filters)
    except Exception as exc:  # noqa: BLE001 — unsafe value or unparsable SQL: never run it
        attempts[-1]["error"] = f"Could not apply the {DB_LABEL[db]} row filter: {exc}"
        return {"attempts": attempts, "final_sql": None}
    if rewritten != sql:
        attempts[-1]["executed"] = rewritten
    return {"attempts": attempts, "final_sql": rewritten}
