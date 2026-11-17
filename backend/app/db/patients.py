"""Patient look-ups for the "view as patient" picker (clinician view, no private columns)."""

from sqlalchemy import Engine, text

from app.db.rls import set_query_context


def _begin(engine: Engine):
    conn = engine.connect()
    trans = conn.begin()
    if engine.dialect.name == "postgresql":
        set_query_context(conn, "clinician", None)
    return conn, trans


def list_patients(engine: Engine) -> list[dict]:
    conn, trans = _begin(engine)
    try:
        rows = conn.execute(text("SELECT id, first, last, birthdate, gender FROM patients")).all()
    finally:
        trans.rollback()
        conn.close()
    people = [
        {"id": r.id, "name": f"{r.first} {r.last}", "birthdate": str(r.birthdate)[:10], "gender": r.gender}
        for r in rows
    ]
    return sorted(people, key=lambda p: p["name"])


def patient_exists(engine: Engine, patient_id: str) -> bool:
    conn, trans = _begin(engine)
    try:
        return conn.execute(text("SELECT 1 FROM patients WHERE id = :id"), {"id": patient_id}).first() is not None
    finally:
        trans.rollback()
        conn.close()
