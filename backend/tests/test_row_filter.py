"""The row-filter rewrite: every mention of a filtered table becomes "only the allowed rows".

Each test runs the rewritten SQL on a tiny SQLite database holding rows for patients p1 and p2
and checks that only p1's rows are visible — behaviour, not string matching.
"""

import pytest
import sqlglot
from sqlalchemy import create_engine, text
from sqlglot import exp

from app.safety.row_filter import RowFilter, UnsafeValueError, restrict_tables

P1 = [RowFilter("claims", "patientid", ["p1"])]


@pytest.fixture(scope="module")
def db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE claims (id TEXT, patientid TEXT, outstandingp REAL)"))
        conn.execute(text("CREATE TABLE claims_transactions (id TEXT, claimid TEXT, patientid TEXT)"))
        conn.execute(text("INSERT INTO claims VALUES ('c1','p1',10), ('c2','p1',0), ('c3','p2',99)"))
        conn.execute(text("INSERT INTO claims_transactions VALUES ('t1','c1','p1'), ('t3','c3','p2')"))
    return engine


def run(db, sql, filters=P1):
    with db.connect() as conn:
        return conn.execute(text(restrict_tables(sql, "mysql", filters))).all()


def test_plain_reference(db):
    assert run(db, "SELECT patientid FROM claims") == [("p1",), ("p1",)]


def test_alias_kept(db):
    assert run(db, "SELECT c.id FROM claims c WHERE c.outstandingp > 0") == [("c1",)]


def test_subquery(db):
    rows = run(db, "SELECT id FROM claims_transactions WHERE claimid IN (SELECT id FROM claims)", [])
    assert len(rows) == 2  # no filter -> unchanged
    rows = run(db, "SELECT id FROM claims_transactions WHERE claimid IN (SELECT id FROM claims)")
    assert rows == [("t1",)]


def test_cte_body(db):
    assert run(db, "WITH t AS (SELECT * FROM claims) SELECT count(*) FROM t") == [(2,)]


def test_cte_named_like_table():
    # Structural check: SQLite (unlike MySQL) treats this as a circular CTE, so it can't run here.
    # The real-MySQL version of this attack is in tests/test_patient_isolation.py.
    out = restrict_tables("WITH claims AS (SELECT * FROM claims) SELECT count(*) FROM claims", "mysql", P1)
    tree = sqlglot.parse_one(out, read="mysql")
    cte_body = tree.find(exp.CTE).this
    assert "patientid = 'p1'" in cte_body.sql(dialect="mysql")  # the real table inside is filtered
    assert out.count("patientid = 'p1'") == 1  # the CTE reference itself is not wrapped again


def test_union(db):
    rows = run(db, "SELECT patientid FROM claims UNION SELECT patientid FROM claims_transactions",
               P1 + [RowFilter("claims_transactions", "patientid", ["p1"])])
    assert rows == [("p1",)]


def test_join_two_filtered_tables(db):
    rows = run(db, "SELECT c.patientid, t.patientid FROM claims c JOIN claims_transactions t ON t.claimid = c.id",
               P1 + [RowFilter("claims_transactions", "patientid", ["p1"])])
    assert rows == [("p1", "p1")]


def test_schema_qualified():
    out = restrict_tables("SELECT count(*) FROM billing_db.claims", "mysql", P1)
    inner = sqlglot.parse_one(out, read="mysql").find(exp.Subquery)
    assert inner is not None and inner.find(exp.Table).db == "billing_db"
    assert "'p1'" in inner.sql(dialect="mysql")


def test_multiple_values_in_list(db):
    rows = run(db, "SELECT id FROM claims ORDER BY id", [RowFilter("claims", "id", ["c1", "c3"])])
    assert rows == [("c1",), ("c3",)]


def test_no_values_returns_nothing(db):
    assert run(db, "SELECT id FROM claims", [RowFilter("claims", "id", [])]) == []


def test_two_filters_same_table_are_anded(db):
    rows = run(db, "SELECT id FROM claims", P1 + [RowFilter("claims", "id", ["c1", "c3"])])
    assert rows == [("c1",)]


@pytest.mark.parametrize("bad", ["x' OR '1'='1", "p1; DROP TABLE claims", "a b", "", "x" * 65])
def test_rejects_unsafe_values(bad):
    with pytest.raises(UnsafeValueError):
        restrict_tables("SELECT id FROM claims", "mysql", [RowFilter("claims", "patientid", [bad])])


def test_many_values(db):
    ids = [f"c{i}" for i in range(1500)]
    assert len(run(db, "SELECT id FROM claims", [RowFilter("claims", "id", ids)])) == 3


def test_duplicate_values_deduplicated():
    out = restrict_tables("SELECT id FROM claims", "mysql", [RowFilter("claims", "id", ["c1", "c1"])])
    assert out.count("'c1'") == 1


def test_unreferenced_table_unchanged():
    sql = "SELECT name FROM providers"
    assert restrict_tables(sql, "mysql", P1) == sqlglot.parse_one(sql, read="mysql").sql(dialect="mysql")


def test_postgres_dialect():
    out = restrict_tables("SELECT count(*) FROM patients p", "postgres", [RowFilter("patients", "id", ["a", "b"])])
    assert "IN ('a', 'b')" in out and "AS p" in out


def test_parenthesised_join_is_kept(db):
    # Final review: table.replace() dropped joins attached to the table inside parentheses.
    out = restrict_tables("SELECT COUNT(*) FROM (claims AS c JOIN claims_transactions AS t ON t.claimid = c.id)", "mysql", P1)
    assert "claims_transactions" in out
    with db.connect() as conn:
        assert conn.execute(text(out)).scalar() == 1  # c1 (p1) has one transaction
