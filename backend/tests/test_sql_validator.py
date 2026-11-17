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


def test_row_to_json_not_on_allowlist_even_for_safe_tables():
    # Stricter since review C1: whole-row JSON is never needed to answer a question.
    assert_rejected("SELECT row_to_json(e) FROM encounters e")


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


# --- Review finding C1: dynamic SQL inside strings (query_to_xml & friends) -----------------
@pytest.mark.parametrize(
    "sql",
    [
        # the verified exploit: switch identity, then count every patient
        "SELECT query_to_xml('select set_config(''app.role'',''clinician'',true)', true, false, '') AS a, "
        "(xpath('count(/table/row)', query_to_xml('select id from patients', true, false, '')))[1]::text AS n",
        "SELECT query_to_xml('select ssn from patients', true, false, '')",
        "SELECT table_to_xml('patients', true, false, '')",
        "SELECT cursor_to_xml('c', 1, true, false, '')",
        "SELECT database_to_xml(true, false, '')",
        "SELECT pg_terminate_backend(123)",
        "SELECT pg_sleep_for('5 minutes')",
        "SELECT pg_advisory_lock(1)",
        "SELECT made_up_function(1)",
    ],
)
def test_rejects_functions_not_on_allowlist(sql):
    assert_rejected(sql)


ANALYTIC_TABLES = {"t", "u"}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*), COUNT(DISTINCT patient), SUM(x), AVG(x), MIN(x), MAX(x) FROM t",
        "SELECT ROUND(AVG(CAST(value AS NUMERIC)), 2), value::numeric, CAST(start AS DATE), start::date FROM t",
        "SELECT date_part('year', age(coalesce(deathdate, now()), birthdate)) FROM t",
        "SELECT EXTRACT(YEAR FROM start), DATE_TRUNC('month', start), CURRENT_DATE, NOW() FROM t",
        "SELECT start > CURRENT_DATE - INTERVAL '1 year', to_char(start, 'YYYY-MM') FROM t",
        "SELECT LOWER(a), UPPER(a), CONCAT(a, ' ', b), a || b, LENGTH(a), SUBSTRING(a, 1, 3), TRIM(a), "
        "REPLACE(a, 'x', 'y'), LEFT(a, 2), split_part(a, ' ', 1), position('x' in a) FROM t",
        "SELECT CASE WHEN a > 1 THEN 'x' ELSE 'y' END, NULLIF(a, 0), GREATEST(a, b), LEAST(a, b), ABS(a), "
        "CEIL(a), FLOOR(a), POWER(a, 2), SQRT(a) FROM t",
        "SELECT ROW_NUMBER() OVER (PARTITION BY p ORDER BY d DESC), RANK() OVER (ORDER BY d), LAG(a) OVER (ORDER BY d) FROM t",
        "SELECT string_agg(a, ', '), array_agg(a), STDDEV(a), PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY a) FROM t",
        "SELECT a FROM t WHERE a ILIKE '%x%' AND b IN (1, 2) AND c BETWEEN 1 AND 2 AND NOT d IS NULL "
        "AND EXISTS (SELECT 1 FROM u)",
    ],
)
def test_allows_common_postgres_functions(sql):
    result = validate_sql(sql, "postgres", ANALYTIC_TABLES, BLOCKED, default_limit=1000)
    assert result.ok, result.error


def test_allows_common_mysql_functions():
    sql = ("SELECT YEAR(d), MONTH(d), DATEDIFF(a, b), TIMESTAMPDIFF(YEAR, a, b), IFNULL(a, 0), IF(a > 1, 'x', 'y'), "
           "GROUP_CONCAT(a SEPARATOR ', '), CURDATE(), DATE_FORMAT(d, '%Y-%m'), DATE_SUB(CURDATE(), INTERVAL 1 YEAR) FROM t")
    result = validate_sql(sql, "mysql", ANALYTIC_TABLES, BLOCKED, default_limit=1000)
    assert result.ok, result.error


# --- Review finding C2: a CTE named after a real table must not hide that table -------------
def test_cte_shadowing_cannot_hide_pii():
    assert_rejected("WITH patients AS (SELECT ssn AS x FROM public.patients) SELECT x FROM patients")
    assert_rejected("WITH patients AS (SELECT * FROM public.patients) SELECT * FROM patients")
    assert_rejected("WITH patients AS (SELECT ssn AS x FROM patients) SELECT x FROM patients")


def test_cte_shadowing_cannot_reach_catalog():
    assert_rejected("WITH pg_stat_activity AS (SELECT * FROM pg_catalog.pg_stat_activity) "
                    "SELECT query FROM pg_stat_activity")
    assert_rejected("WITH patients AS (SELECT usename FROM pg_user) SELECT usename FROM patients")


def test_normal_cte_still_allowed():
    sql = "WITH d AS (SELECT patient FROM conditions WHERE description ILIKE '%diabetes%') SELECT count(*) FROM d"
    assert check(sql).ok


def test_tables_in_with_shadowing_cte():
    assert tables_in("WITH patients AS (SELECT id FROM conditions) SELECT id FROM patients", "postgres") == ["conditions"]


def test_tables_in():
    sql = "WITH x AS (SELECT patient FROM conditions) SELECT p.first FROM patients p JOIN x ON x.patient = p.id"
    assert tables_in(sql, "postgres") == ["conditions", "patients"]


# --- Final review (Plan 2), Critical: a table aliased with another table's name ----------
@pytest.mark.parametrize("sql", [
    "SELECT encounters.ssn AS x FROM patients AS encounters JOIN encounters AS e ON e.patient = encounters.id",
    "SELECT conditions.passport FROM patients conditions, conditions c",
])
def test_alias_named_like_another_table_cannot_hide_pii(sql):
    assert_rejected(sql)


def test_alias_collision_cannot_hide_population_columns():
    blocked = {"payers.amount_covered", "payers.revenue"}
    for sql in ["SELECT claims.name, claims.amount_covered, claims.revenue FROM payers AS claims CROSS JOIN claims AS c2",
                "SELECT claims.amount_covered FROM payers AS claims JOIN claims AS c2 ON c2.primarypatientinsuranceid = claims.id"]:
        result = validate_sql(sql, "mysql", {"payers", "claims"}, blocked, default_limit=1000)
        assert not result.ok, sql


def test_aliased_tables_still_work():
    assert check("SELECT p.first, e.description FROM patients p JOIN encounters e ON e.patient = p.id").ok


def test_tokenizer_error_is_a_rejection_not_a_crash():
    # Final review: an unterminated string raised TokenError and crashed the whole answer.
    result = validate_sql("SELECT 'abc FROM patients", "mysql", ALLOWED, BLOCKED, default_limit=1000)
    assert not result.ok and result.error
