"""Step: EXECUTE — run the approved query on the database.

Plain English:
  1. Open a transaction on the read-only connection.
  2. PostgreSQL: pin "who is asking" (clinician / patient X) so row-level security filters rows.
  3. Run the query and fetch at most ROWS_STORED_CAP rows (+1, to know if there were more).
  4. As a last safety net, drop any private column (ssn/drivers/passport) that slipped through.
  5. Convert values (dates, decimals, ids) into plain JSON-friendly forms.
If the database complains (e.g. "column does not exist"), the error is recorded on the
attempt, and the retry decision sends it back to the AI to fix.

The query runs through the driver's raw cursor with no parameters, so characters like
'%' in LIKE patterns or ':' in text are passed to the database exactly as written.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from app.db.engines import DB_LABEL
from app.db.rls import set_query_context
from app.graph.deps import Deps
from app.graph.nodes.validate import DIALECTS
from app.graph.state import ChatState, QueryResult
from app.graph.timing import timed
from app.safety.sql_validator import tables_in


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
