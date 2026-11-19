"""Ties in "top N" lists: ORDER BY ... LIMIT N cuts tied rows arbitrarily, so code re-runs the query keeping them.

Live (2026-11-19): "Which patient owes us the most? top 5" — at least five patients owe exactly 42.28, and
LIMIT 5 silently picked three of them."""

import pytest
import sqlglot

from app.db.ties import RANK_COLUMN, with_ties


def _sql(text, dialect="postgres"):
    out = with_ties(text, dialect)
    assert out is not None, text
    return out


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_top_n_becomes_rank_with_ties(dialect):
    sql, n = _sql("SELECT patientid, SUM(outstandingp) AS total FROM claims GROUP BY patientid "
                  "ORDER BY total DESC LIMIT 5", dialect)
    assert n == 5
    tree = sqlglot.parse_one(sql, read=dialect)
    assert "RANK() OVER (ORDER BY SUM(outstandingp) DESC)" in sql  # alias replaced by its expression
    assert f"{RANK_COLUMN} <= 5" in sql and tree.args.get("limit") is None


def test_ordinal_order_key_is_resolved():
    sql, _ = _sql("SELECT name, revenue FROM payers ORDER BY 2 DESC LIMIT 3")
    assert "RANK() OVER (ORDER BY revenue DESC)" in sql


@pytest.mark.parametrize("text", [
    "SELECT name FROM payers ORDER BY revenue DESC",                     # no LIMIT: nothing is cut
    "SELECT name FROM payers LIMIT 5",                                   # no ORDER BY: no ranking
    "SELECT name FROM payers ORDER BY revenue DESC LIMIT 5 OFFSET 5",    # paging
    "SELECT DISTINCT name FROM payers ORDER BY name LIMIT 5",            # DISTINCT runs after windows
    "SELECT * FROM payers ORDER BY revenue DESC LIMIT 5",                # unknown/duplicate output names
    "SELECT p.id, e.id FROM patients p JOIN encounters e ON e.patient = p.id ORDER BY e.start LIMIT 5",
    "SELECT name FROM payers ORDER BY revenue DESC LIMIT 1000",          # not a "top N"
    "SELECT name, RANK() OVER (ORDER BY revenue) AS r FROM payers ORDER BY r LIMIT 5",  # already windowed
    "SELECT name FROM payers UNION SELECT name FROM organizations ORDER BY name LIMIT 5",
])
def test_left_alone(text):
    assert with_ties(text, "postgres") is None


def test_unparseable_sql_is_left_alone():
    assert with_ties("SELEKT nonsense", "postgres") is None
