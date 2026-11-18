"""Computing the true answer for a test question, straight from the databases.

Plain English: for each test question we wrote our own trusted SQL. It runs with the ADMIN
account (no privacy filter — we need the full truth to judge against), at the moment the report
is made, so the truth always matches the data. A two-step question (e.g. "which doctor...":
visits are in PostgreSQL, names in MySQL) runs the first step, then feeds its values (:prev)
into the second step on the other database.
"""

from typing import Any

from sqlalchemy import Engine, bindparam, text

from app.eval.cases import Gold


def compute_gold(gold: Gold, engines: dict[str, Engine], patient_id: str | None) -> list[list[Any]]:
    rows = _run(gold, engines, {"patient_id": patient_id})
    if gold.then is not None:
        prev = [r[0] for r in rows if r and r[0] is not None]
        if not prev:
            return []
        rows = _run(gold.then, engines, {"patient_id": patient_id, "prev": prev})
    return rows


def _run(gold: Gold, engines: dict[str, Engine], params: dict) -> list[list[Any]]:
    stmt = text(gold.sql)
    if ":prev" in gold.sql:
        stmt = stmt.bindparams(bindparam("prev", expanding=True))
    used = {k: v for k, v in params.items() if f":{k}" in gold.sql}
    with engines[gold.db].connect() as conn:
        return [list(r) for r in conn.execute(stmt, used)]
