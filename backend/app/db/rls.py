"""Who is asking? — tell PostgreSQL before each query.

Plain English: PostgreSQL has a built-in privacy filter called Row-Level Security (RLS).
Every patient table has a rule: "show a row only if the asker is a clinician, OR the row
belongs to the patient who is asking". Before running a query we pin two notes onto the
current transaction: app.role and app.patient_id. The database reads those notes and
filters rows itself — so even a badly written query can't see other patients.

The notes are *transaction-local* (the `true` argument): they vanish when the
transaction ends, so a reused connection never remembers the previous person.
"""

from typing import Literal

from sqlalchemy import Connection, text


def set_query_context(conn: Connection, role: Literal["clinician", "patient"], patient_id: str | None) -> None:
    if role == "patient" and not patient_id:
        raise ValueError("patient role requires a patient_id")
    if role not in ("clinician", "patient"):
        raise ValueError(f"unknown role: {role!r}")
    conn.execute(
        text("SELECT set_config('app.role', :role, true), set_config('app.patient_id', :pid, true)"),
        {"role": role, "pid": patient_id or ""},
    )
