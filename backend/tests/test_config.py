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


def test_api_port_default_and_override(monkeypatch):
    assert Settings(_env_file=None).api_port == 8000
    monkeypatch.setenv("AETHER_API_PORT", "8001")
    assert Settings(_env_file=None).api_port == 8001


# Deployment (2026-11-25): Neon, Aiven and TiDB only accept encrypted connections, and the website on Vercel
# lives at a different address from the backend on Render.
def test_cloud_postgres_asks_for_ssl():
    assert make().clinical_url().endswith("/clinical_db")                      # local: unchanged
    assert make(pg_sslmode="require").clinical_url().endswith("/clinical_db?sslmode=require")


def test_cloud_mysql_verifies_the_server_certificate():
    assert "ssl_ca" not in make().billing_url()
    url = make(mysql_ssl_ca="/etc/secrets/ca.pem").billing_url()
    assert url.endswith("/billing_db?charset=utf8mb4&ssl_ca=%2Fetc%2Fsecrets%2Fca.pem")


def test_the_website_address_is_read_as_a_list():
    assert make().cors_origin_list() == []
    s = make(cors_origins="https://aether.vercel.app, https://aether-git-main.vercel.app/")
    assert s.cors_origin_list() == ["https://aether.vercel.app", "https://aether-git-main.vercel.app"]


def test_the_deployed_website_may_call_the_api_and_others_may_not(monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import create_app
    monkeypatch.setenv("CORS_ORIGINS", "https://aether.vercel.app")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(with_pipeline=False))
        ask = lambda origin: client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})  # noqa: E731
        assert ask("https://aether.vercel.app").headers.get("access-control-allow-origin") == "https://aether.vercel.app"
        assert "access-control-allow-origin" not in ask("https://evil.example").headers
        assert ask("http://localhost:5173").headers.get("access-control-allow-origin") == "http://localhost:5173"
    finally:
        get_settings.cache_clear()
