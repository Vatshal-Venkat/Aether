"""The row filter — "you may only see these rows", added by code to the AI's SQL.

Plain English: MySQL has no built-in per-patient privacy filter (PostgreSQL does: RLS).
So before a query runs, we rewrite it. Every place the query reads a protected table, e.g.

    SELECT sum(outstandingp) FROM claims c

the table is swapped for a pre-filtered copy of itself:

    SELECT sum(outstandingp) FROM (SELECT * FROM claims WHERE patientid = 'p1') AS c

This happens everywhere the table appears — joins, subqueries, WITH blocks, UNIONs — because
we edit the parsed query tree (sqlglot), not the text. However the AI wrote the query, it
can only ever see the allowed rows.

The same tool links two databases: "of providers, keep only the ids step 1 found".

The values (patient ids, ids from step 1) are put in by code, never by the AI, and each must
look like an id (letters, digits, - _ . :) — anything else is refused, so a value can never
smuggle SQL in.
"""

import re
from typing import NamedTuple

import sqlglot
from sqlglot import exp

from app.safety.sql_validator import Dialect, _real_tables

SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class UnsafeValueError(ValueError):
    """A filter value that does not look like an id."""


class RowFilter(NamedTuple):
    table: str          # e.g. "claims"
    column: str         # e.g. "patientid"
    values: list[str]   # allowed values of that column


def _condition(filters: list[RowFilter]) -> exp.Expression:
    parts: list[exp.Expression] = []
    for f in filters:
        values = list(dict.fromkeys(f.values))  # dedupe, keep order
        for v in values:
            if not isinstance(v, str) or not SAFE_VALUE.match(v):
                raise UnsafeValueError(f"refusing unsafe filter value {v!r} for {f.table}.{f.column}")
        column = exp.column(f.column)
        if not values:
            parts.append(exp.EQ(this=exp.Literal.number(1), expression=exp.Literal.number(0)))
        elif len(values) == 1:
            parts.append(exp.EQ(this=column, expression=exp.Literal.string(values[0])))
        else:
            parts.append(exp.In(this=column, expressions=[exp.Literal.string(v) for v in values]))
    return exp.and_(*parts) if len(parts) > 1 else parts[0]


def restrict_tables(sql: str, dialect: Dialect, filters: list[RowFilter]) -> str:
    """Rewrite `sql` so every real reference to a filtered table only sees the allowed rows."""
    tree = sqlglot.parse_one(sql, read=dialect)
    by_table: dict[str, list[RowFilter]] = {}
    for f in filters:
        by_table.setdefault(f.table.lower(), []).append(f)
    conditions = {table: _condition(fs) for table, fs in by_table.items()}  # validates values up front

    # Collect first, then replace: the new inner SELECTs must not be rewritten again.
    targets = [t for t in _real_tables(tree) if t.name.lower() in conditions]
    for table in targets:
        source = exp.Table(this=exp.to_identifier(table.name),
                           db=exp.to_identifier(table.db) if table.db else None)
        inner = exp.select("*").from_(source).where(conditions[table.name.lower()].copy())
        wrapped = exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(table.alias_or_name)))
        # "FROM (claims c JOIN payers p ...)": sqlglot hangs the JOINs on the table node itself —
        # carry them over, or the join would silently disappear (found in final review).
        for key in ("joins", "laterals", "pivots"):
            if table.args.get(key):
                wrapped.set(key, table.args[key])
        table.replace(wrapped)
    return tree.sql(dialect=dialect)
