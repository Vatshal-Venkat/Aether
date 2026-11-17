"""Small helpers inside the setup script."""

from scripts.setup_databases import _server_url, _sql_literal


def test_server_url_removes_database():
    url = _server_url("mysql+pymysql://root:pw@localhost:3306/billing_db?charset=utf8mb4", None)
    assert "billing_db" not in url
    assert url.startswith("mysql+pymysql://root:pw@localhost:3306")


def test_server_url_switches_database():
    url = _server_url("postgresql+psycopg://postgres:pw@localhost:5432/clinical_db", "postgres")
    assert url.endswith("/postgres")


def test_sql_literal_escapes_quotes():
    assert _sql_literal("it's") == "'it''s'"
