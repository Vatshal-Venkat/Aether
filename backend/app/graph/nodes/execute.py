"""Step: EXECUTE — run the approved query on the database.

Plain English:
  1. Open a transaction on the read-only connection.
  2. PostgreSQL: pin "who is asking" (clinician / patient X) so row-level security filters rows.
  3. Run the query and fetch at most ROWS_STORED_CAP rows (+1, to know if there were more).
  4. As a last safety net, drop any private column (ssn/drivers/passport) that slipped through.
  5. Convert values (dates, decimals, ids) into plain JSON-friendly forms.
If the database complains (e.g. "column does not exist"), the error is recorded on the
attempt, and the retry decision sends it back to the AI to fix. In step 1 of a two-database
plan, a result without the linking column (e.g. provider) also counts as a failed try.

The query runs through the driver's raw cursor with no parameters, so characters like
'%' in LIKE patterns or ':' in text are passed to the database exactly as written.
"""

import datetime as dt
import logging
import uuid
from decimal import Decimal
from typing import Any

from app.db.engines import DB_LABEL
from app.db.rls import set_query_context
from app.db.ties import with_ties
from app.graph.deps import Deps
from app.graph.nodes.validate import DIALECTS
from app.graph.state import ChatState, QueryResult
from app.graph.timing import timed
from app.safety.sql_validator import tables_in


log = logging.getLogger(__name__)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


@timed("execute")
def execute(state: ChatState, deps: Deps) -> dict:
    db = state["db"]
    engine = deps.engines[db]
    cap = deps.settings.rows_stored_cap
    pii_names = {c.split(".", 1)[1] for c in deps.glossary.pii_columns}
    attempts = [dict(a) for a in state["attempts"]]
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                set_query_context(conn, state["role"], state.get("patient_id"))
            cursor = conn.connection.cursor()
            try:
                cursor.execute(state["final_sql"])
                columns = [d[0] for d in cursor.description]
                raw_rows = cursor.fetchmany(cap + 1)
            finally:
                cursor.close()
    except Exception as exc:  # noqa: BLE001 — any database error goes back to the AI
        attempts[-1]["error"] = str(exc).strip().splitlines()[0][:300]
        return {"attempts": attempts, "result": None}

    link = state.get("link")
    if link and state.get("step", 0) == 0 and link.from_column.lower() not in {c.lower() for c in columns}:
        attempts[-1]["error"] = (f"Include the column {link.from_column} (from {link.from_table}) in the output, "
                                 "unaliased — the next step needs it to look up matching rows.")
        return {"attempts": attempts, "result": None}

    tied = with_ties(state["final_sql"], DIALECTS[db])
    if tied and len(raw_rows) == tied[1]:
        # Exactly N rows from "ORDER BY ... LIMIT N": rows tied with the N-th may have been cut. Re-run keeping
        # them (with a "ranking" column). If that fails for any reason, the original result stands.
        try:
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    set_query_context(conn, state["role"], state.get("patient_id"))
                cursor = conn.connection.cursor()
                try:
                    cursor.execute(tied[0])
                    tie_columns = [d[0] for d in cursor.description]
                    tie_rows = cursor.fetchmany(cap + 1)
                finally:
                    cursor.close()
            if len(tie_rows) > len(raw_rows):  # only when ties really were cut off
                columns, raw_rows = tie_columns, tie_rows
                attempts[-1]["executed"] = tied[0]  # the SQL panel shows what really ran
        except Exception:  # noqa: BLE001 — keeping ties is a nicety; never lose a correct answer over it
            log.warning("tie-keeping query failed; keeping the original top-%d result", tied[1], exc_info=True)

    keep = [i for i, c in enumerate(columns) if c.lower() not in pii_names]
    rows = [[json_safe(r[i]) for i in keep] for r in raw_rows[:cap]]
    result = QueryResult(
        columns=[columns[i] for i in keep],
        rows=rows,
        total_rows=len(rows),
        truncated=len(raw_rows) > cap,
    )
    sources = [f"{DB_LABEL[db]}.{t}" for t in tables_in(state["final_sql"], DIALECTS[db])]
    return {"attempts": attempts, "result": result, "sources": sources}
