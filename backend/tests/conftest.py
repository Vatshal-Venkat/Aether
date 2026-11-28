"""Shared test helpers.

Tests that need the real databases are marked @pytest.mark.db and are skipped (with a
reason) when PostgreSQL/MySQL can't be reached as the read-only chatbot user.
"""

from functools import lru_cache
from typing import Literal

import pytest
from sqlalchemy import create_engine, text

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_ai_env(monkeypatch):
    """Tests must not depend on AI keys/settings set in the developer's OS environment."""
    for var in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("RAG_LIVE_FALLBACK", "false")  # no live openFDA calls; tests/rag/test_live.py turns it on


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, pg_admin_password="pg", mysql_admin_password="my", ro_password="ro")


@lru_cache
def _db_problem(kind: Literal["clinical", "billing"]) -> str | None:
    s = get_settings()
    url = s.clinical_url() if kind == "clinical" else s.billing_url()
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return None
    except Exception as exc:  # noqa: BLE001 — any failure means "skip"
        return f"{kind} database not reachable as chatbot_ro: {str(exc).splitlines()[0][:120]}"


def requires_db(kind: Literal["clinical", "billing"]) -> None:
    """Call at the start of a db test: skips it when that database isn't available."""
    problem = _db_problem(kind)
    if problem:
        pytest.skip(problem)
