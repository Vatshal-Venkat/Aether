"""Who is asking? — tell PostgreSQL before each query, with a signature it can check.

Plain English: PostgreSQL has a built-in privacy filter called Row-Level Security (RLS).
Every patient table has a rule: "show a row only if the asker is a clinician, OR the row
belongs to the patient who is asking". Before running a query we pin three notes onto the
current transaction: app.role, app.patient_id and app.sig.

app.sig is a signature: a fingerprint (SHA-256) of a secret key + role + patient id. The key
is stored in a table the chatbot's account cannot read. The database recomputes the
fingerprint for every row it shows; if someone changed the notes (say, a query that rewrites
app.role to 'clinician' part-way through), the fingerprint no longer matches and nothing is
shown. The SQL safety check already blocks such tricks — this is a second lock on the door.

The notes are *transaction-local* (the `true` argument): they vanish when the
transaction ends, so a reused connection never remembers the previous person.
"""

import hashlib
from typing import Literal

from sqlalchemy import Connection, text

from app.config import get_settings


def identity_signature(key: str, role: str, patient_id: str | None) -> str:
    """Fingerprint of key|role|patient_id — PostgreSQL computes exactly the same thing."""
    return hashlib.sha256(f"{key}|{role}|{patient_id or ''}".encode()).hexdigest()


def set_query_context(conn: Connection, role: Literal["clinician", "patient"], patient_id: str | None) -> None:
    if role == "patient" and not patient_id:
        raise ValueError("patient role requires a patient_id")
    if role not in ("clinician", "patient"):
        raise ValueError(f"unknown role: {role!r}")
    pid = patient_id or ""
    sig = identity_signature(get_settings().rls_key(), role, pid)
    conn.execute(
        text("SELECT set_config('app.role', :role, true), set_config('app.patient_id', :pid, true), "
             "set_config('app.sig', :sig, true)"),
        {"role": role, "pid": pid, "sig": sig},
    )
