"""SQL safety checker: AI-written SQL must be a single, read-only, PII-free SELECT over known tables."""

import pytest

from app.safety.sql_validator import tables_in, validate_sql

ALLOWED = {"patients", "encounters", "conditions", "observations"}
BLOCKED = {"patients.ssn", "patients.drivers", "patients.passport"}


def check(sql: str, dialect: str = "postgres"):
    return validate_sql(sql, dialect, ALLOWED, BLOCKED, default_limit=1000)


def assert_rejected(sql: str, dialect: str = "postgres", contains: str | None = None):
    result = check(sql, dialect)
    assert not result.ok, f"should be rejected: {sql}"
    assert result.sql is None and result.error
    if contains:
        assert contains.lower() in result.error.lower()


def test_accepts_simple_select():
    result = check("SELECT first, last FROM patients WHERE gender = 'F'")
    assert result.ok and result.error is None
    assert "FROM patients" in result.sql


def test_accepts_cte_and_join():
    sql = """
        WITH diabetic AS (SELECT DISTINCT patient FROM conditions WHERE description ILIKE '%diabetes%')
        SELECT p.first, count(e.id) AS visits
        FROM patients p JOIN diabetic d ON d.patient = p.id JOIN encounters e ON e.patient = p.id
        GROUP BY p.first
    """
    assert check(sql).ok


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO patients (id) VALUES ('x')",
        "UPDATE patients SET first = 'x'",
        "DELETE FROM patients",
        "DROP TABLE patients",
        "CREATE TABLE t (x INT)",
        "ALTER TABLE patients ADD COLUMN x INT",
        "TRUNCATE TABLE patients",
        "GRANT SELECT ON patients TO public",
    ],
)
def test_rejects_dml(sql):
    assert_rejected(sql)


def test_rejects_multiple_statements():
    assert_rejected("SELECT 1; DROP TABLE patients")
    assert_rejected("SELECT id FROM patients -- harmless?\n; DELETE FROM patients")


def test_rejects_into_outfile():
    assert_rejected("SELECT id FROM patients INTO OUTFILE '/tmp/x.csv'", dialect="mysql")
    assert_rejected("SELECT id INTO stolen FROM patients")


def test_rejects_identity_functions():
    assert_rejected(
        "SELECT id FROM patients WHERE set_config('app.patient_id', 'someone-else', true) IS NOT NULL",
        contains="set_config",
    )
    assert_rejected("SELECT current_setting('app.role')", contains="current_setting")


def test_rejects_sleep():
    assert_rejected("SELECT pg_sleep(30)")
    assert_rejected("SELECT SLEEP(30)", dialect="mysql")


def test_rejects_unknown_table():
    assert_rejected("SELECT * FROM pg_roles", contains="pg_roles")
    assert_rejected("SELECT table_name FROM information_schema.tables")


def test_rejects_pii_column():
    assert_rejected("SELECT ssn FROM patients", contains="ssn")
    assert_rejected("SELECT p.passport FROM patients p")
    assert_rejected("WITH x AS (SELECT drivers FROM patients) SELECT * FROM x")


def test_rejects_star_on_pii_table():
    assert_rejected("SELECT * FROM patients")
    assert_rejected("SELECT p.* FROM patients p JOIN encounters e ON e.patient = p.id")


def test_rejects_whole_row_reference_to_pii_table():
    # In Postgres a bare table alias is the whole row (every column, SSN included).
    assert_rejected("SELECT row_to_json(p) FROM patients p")
    assert_rejected("SELECT row_to_json(patients) FROM patients")
    assert_rejected("SELECT p FROM patients p")


def test_allows_whole_row_of_safe_table():
    assert check("SELECT row_to_json(e) FROM encounters e").ok


def test_allows_star_on_safe_table_and_count_star():
    assert check("SELECT * FROM conditions").ok
    assert check("SELECT count(*) FROM patients").ok
    assert check("SELECT e.* FROM encounters e JOIN patients p ON p.id = e.patient").ok


def test_adds_limit():
    assert "LIMIT 1000" in check("SELECT first FROM patients").sql


def test_keeps_existing_limit():
    sql = check("SELECT first FROM patients ORDER BY first LIMIT 5").sql
    assert "LIMIT 5" in sql and "LIMIT 1000" not in sql


def test_unparseable_sql_rejected():
    assert_rejected("SELEC first FROM", contains="")


def test_tables_in():
    sql = "WITH x AS (SELECT patient FROM conditions) SELECT p.first FROM patients p JOIN x ON x.patient = p.id"
    assert tables_in(sql, "postgres") == ["conditions", "patients"]
