"""The SQL safety checker.

Plain English: before any AI-written SQL touches a database, this module reads it the way
a compiler would — it turns the text into a tree of parts (an "abstract syntax tree", via
the sqlglot library) and inspects every part. Text matching ("does it contain DELETE?")
is easy to fool; a parsed tree is not.

A query passes only if it is:
  * exactly ONE statement, and a read-only SELECT (no INSERT/UPDATE/DELETE/DROP/... anywhere);
  * not writing results somewhere (SELECT ... INTO);
  * not calling dangerous functions — including set_config/current_setting, which could
    let a query change "who is asking" in the middle of running;
  * only using tables from our catalog;
  * never touching private columns (SSN, driver's licence, passport), even via SELECT *.
It also adds a LIMIT so nobody accidentally pulls a million rows.

Every rejection message is phrased as an instruction, because it is fed back to the AI
so it can fix its own query (the "self-correction" loop).
"""

from dataclasses import dataclass
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

Dialect = Literal["postgres", "mysql"]

BLOCKED_FUNCTIONS = {
    "set_config", "current_setting", "pg_sleep", "sleep", "benchmark", "load_file",
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "lo_import", "lo_export", "dblink", "copy",
}

_WRITE_NODES = tuple(
    getattr(exp, name)
    for name in ("Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable", "Command", "Grant")
    if hasattr(exp, name)
)

_ALLOWED_SCHEMAS = {"", "public", "clinical_db", "billing_db"}


@dataclass
class ValidationResult:
    ok: bool
    sql: str | None = None
    error: str | None = None


def _fail(message: str) -> ValidationResult:
    return ValidationResult(ok=False, error=message)


def _function_names(fn: exp.Func) -> set[str]:
    names = {type(fn).__name__.lower()}
    if isinstance(fn, exp.Anonymous):
        names.add(str(fn.name).lower())
    else:
        names.add(fn.sql_name().lower())
    return names


def _real_tables(tree: exp.Expression) -> list[exp.Table]:
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    return [t for t in tree.find_all(exp.Table) if t.name.lower() not in cte_names]


def validate_sql(
    sql: str,
    dialect: Dialect,
    allowed_tables: set[str],
    blocked_columns: set[str],
    default_limit: int,
) -> ValidationResult:
    # 1. Parse into a syntax tree.
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except ParseError as exc:
        return _fail(f"The SQL could not be parsed ({str(exc).splitlines()[0]}). Write one valid {dialect} SELECT.")
    if len(statements) != 1:
        return _fail("Write exactly one SQL statement (no semicolon-separated statements).")
    tree = statements[0]

    # 2. Read-only SELECT only.
    if not isinstance(tree, exp.Query) or tree.find(*_WRITE_NODES):
        return _fail("Only read-only SELECT queries are allowed.")
    if tree.find(exp.Into) or tree.args.get("into"):
        return _fail("SELECT ... INTO is not allowed; just return the rows.")

    # 3. Dangerous functions.
    for fn in tree.find_all(exp.Func):
        bad = _function_names(fn) & BLOCKED_FUNCTIONS
        if bad:
            return _fail(f"The function {sorted(bad)[0]}() is not allowed.")

    # 4. Known tables only.
    tables = _real_tables(tree)
    alias_to_table: dict[str, str] = {}
    for t in tables:
        name = t.name.lower()
        schema = (t.db or "").lower()
        if t.catalog or schema not in _ALLOWED_SCHEMAS or name not in allowed_tables:
            return _fail(f"Table '{t.sql()}' is not available. Use only: {', '.join(sorted(allowed_tables))}.")
        alias_to_table[t.alias_or_name.lower()] = name
        alias_to_table[name] = name
    referenced = set(alias_to_table.values())
    blocked = {b.lower() for b in blocked_columns}
    tables_with_blocked = {b.split(".", 1)[0] for b in blocked}

    # 5. Private columns — directly, or hidden behind * / t.*.
    for col in tree.find_all(exp.Column):
        qualifier = col.table.lower() if col.table else ""
        if isinstance(col.this, exp.Star):  # t.*
            if alias_to_table.get(qualifier) in tables_with_blocked:
                return _fail(f"Do not use {qualifier}.* on a table with private columns; list the columns you need.")
            continue
        name = col.name.lower()
        if not qualifier and alias_to_table.get(name) in tables_with_blocked:
            # Bare table name/alias used as a value = the WHOLE row (e.g. row_to_json(p)).
            return _fail(f"Do not reference the whole row '{name}'; list the columns you need.")
        owners = [alias_to_table[qualifier]] if qualifier in alias_to_table else referenced
        for owner in owners:
            if f"{owner}.{name}" in blocked:
                return _fail(f"The column {owner}.{name} is private and must not be selected.")
    for star in tree.find_all(exp.Star):
        if isinstance(star.parent, (exp.Count, exp.Column)):
            continue  # count(*) is fine; t.* handled above
        if referenced & tables_with_blocked:
            return _fail("Do not use SELECT * on tables with private columns; list the columns you need.")

    # 6. Always cap the number of rows.
    if not tree.args.get("limit"):
        tree = tree.limit(default_limit)

    return ValidationResult(ok=True, sql=tree.sql(dialect=dialect))


def tables_in(sql: str, dialect: Dialect) -> list[str]:
    """Names of the real tables a query reads (CTE names excluded), sorted."""
    tree = sqlglot.parse_one(sql, read=dialect)
    return sorted({t.name.lower() for t in _real_tables(tree)})
