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


def test_identity_sql_statements_keep_function_body_whole():
    from scripts.setup_databases import IDENTITY_SQL, _statements
    stmts = _statements(IDENTITY_SQL.read_text())
    fn = [s for s in stmts if "CREATE OR REPLACE FUNCTION" in s]
    assert len(fn) == 1 and fn[0].rstrip().endswith("$$")
    assert any(":key" in s for s in stmts)
    assert not any(s.lstrip().startswith("--") for s in stmts)


def test_rls_only_flag_skips_data_load(monkeypatch):
    import scripts.setup_databases as sd
    calls = []
    monkeypatch.setattr(sd, "download_synthea", lambda *a: calls.append("download"))
    monkeypatch.setattr(sd, "load_tables", lambda *a: calls.append("load"))
    monkeypatch.setattr(sd, "create_databases", lambda *a: calls.append("create"))
    monkeypatch.setattr(sd, "apply_postgres_rls", lambda pg, key: calls.append("rls"))
    monkeypatch.setattr(sd, "create_engine", lambda url: type("E", (), {"dispose": lambda self: None})())
    monkeypatch.setattr(sd, "get_settings", lambda: sd.Settings(_env_file=None, pg_admin_password="a",
                                                                  mysql_admin_password="b", ro_password="c"))
    assert sd.main(["--rls-only"]) == 0
    assert calls == ["rls"]
