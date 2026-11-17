"""Connections to the two databases.

Plain English: an "engine" is the app's phone line to a database. We keep a small pool of
open lines (so we don't redial for every question), always log in as the read-only
chatbot_ro account, and set a stopwatch: any query running longer than
SQL_TIMEOUT_SECONDS is cancelled by the database itself.
"""

from functools import lru_cache
from typing import Literal

from sqlalchemy import Engine, create_engine, event, text

from app.config import get_settings

DbName = Literal["clinical", "billing"]

DB_LABEL: dict[DbName, str] = {"clinical": "clinical_db", "billing": "billing_db"}


@lru_cache
def get_engine(db: DbName) -> Engine:
    s = get_settings()
    timeout_ms = s.sql_timeout_seconds * 1000
    if db == "clinical":
        return create_engine(
            s.clinical_url(),
            pool_pre_ping=True,
            pool_size=5,
            connect_args={"options": f"-c statement_timeout={timeout_ms}", "connect_timeout": 5},
        )
    engine = create_engine(s.billing_url(), pool_pre_ping=True, pool_size=5, connect_args={"connect_timeout": 5})

    @event.listens_for(engine, "connect")
    def _set_mysql_timeout(dbapi_conn, _record):  # MySQL's per-session query stopwatch
        with dbapi_conn.cursor() as cur:
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}")

    return engine


def check_db(db: DbName) -> str:
    """'ok' if we can run SELECT 1, else 'error: <first line of the problem>'."""
    try:
        with get_engine(db).connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 — health must never crash
        return f"error: {str(exc).splitlines()[0][:150]}"
