"""Settings: where the app reads its configuration (database addresses, passwords, AI provider)."""

from app.config import Settings


def make(**overrides) -> Settings:
    # _env_file=None so tests never read the real backend/.env
    base = dict(pg_admin_password="pgadmin", mysql_admin_password="myadmin", ro_password="ro")
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_defaults():
    s = make()
    assert s.llm_provider == "groq"
    assert s.sql_timeout_seconds == 10
    assert s.max_sql_attempts == 3
    assert s.rows_stored_cap == 1000
    assert s.rows_to_llm == 50


def test_clinical_url_uses_ro_user():
    assert "chatbot_ro:ro@localhost:5432/clinical_db" in make().clinical_url()
    assert make().clinical_url().startswith("postgresql+psycopg://")


def test_billing_url_uses_ro_user():
    url = make().billing_url()
    assert url.startswith("mysql+pymysql://chatbot_ro:ro@localhost:3306/billing_db")


def test_admin_url_uses_admin_user():
    assert "postgres:pgadmin@" in make().clinical_url(admin=True)
    assert "root:myadmin@" in make().billing_url(admin=True)


def test_password_is_url_encoded():
    assert "p%40ss%2Fword" in make(ro_password="p@ss/word").clinical_url()


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert make().llm_provider == "gemini"


def test_rls_key_derived_when_unset():
    import hashlib
    s = Settings(_env_file=None, pg_admin_password="pg")
    assert s.rls_key() == hashlib.sha256(b"aether-rls|pg").hexdigest()


def test_rls_key_explicit():
    assert Settings(_env_file=None, pg_admin_password="pg", rls_secret="k").rls_key() == "k"
