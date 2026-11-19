"""Ties in "top N" lists.

Plain English: "top 5" is usually written ORDER BY amount DESC LIMIT 5. If the 5th and 6th rows have the same
amount, LIMIT picks one of them at random and hides the other, so the answer is quietly unfair. When a query
like that returns exactly N rows, we run it once more as "rank every row by the same ordering and keep
everyone ranked N or better" (RANK() gives tied rows the same number: 1, 2, 3, 3, 3, 3, 3). The rank is
returned as an extra "ranking" column, so the answer can say who is tied.

This only wraps a query that was already checked and filtered — it adds a ranking, nothing else. Anything
unusual (paging, DISTINCT, SELECT *, duplicate column names, existing window functions, set operations)
is left alone. If the wrapped query fails, the caller keeps the original result.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

RANK_COLUMN = "ranking"
MAX_TOP_N = 100  # bigger LIMITs are page-sized cut-offs, not "top N" questions


def _order_key(key: exp.Expression, projections: list[exp.Expression]) -> exp.Expression | None:
    """ORDER BY may name an output alias or position; a window's ORDER BY needs the real expression."""
    if isinstance(key, exp.Literal) and key.is_int:
        i = int(key.this) - 1
        return projections[i].unalias().copy() if 0 <= i < len(projections) else None
    if isinstance(key, exp.Column) and not key.table:
        for p in projections:
            if isinstance(p, exp.Alias) and p.alias.lower() == key.name.lower():
                return p.unalias().copy()
    return key.copy()


def with_ties(sql: str, dialect: str) -> tuple[str, int] | None:
    """(query that keeps rows tied with the N-th, N) for a top-N query; None when it doesn't apply."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except SqlglotError:
        return None
    if not isinstance(tree, exp.Select) or tree.args.get("distinct") or tree.args.get("offset"):
        return None
    limit, order = tree.args.get("limit"), tree.args.get("order")
    count = limit.expression if limit else None
    if order is None or not isinstance(count, exp.Literal) or not count.is_int:
        return None
    n = int(count.this)
    if not 1 <= n <= MAX_TOP_N:
        return None

    projections = tree.expressions
    names = [p.alias_or_name.lower() for p in projections]
    stars = any(isinstance(p, exp.Star) or (isinstance(p, exp.Column) and isinstance(p.this, exp.Star))
                for p in projections)  # SELECT * / t.* (COUNT(*) is fine)
    if (stars or "" in names or len(set(names)) != len(names) or RANK_COLUMN in names
            or any(p.find(exp.Window) for p in projections)):
        return None

    keys = []
    for ordered in order.expressions:
        key = _order_key(ordered.this, projections)
        if key is None or key.find(exp.Window):
            return None
        keys.append(exp.Ordered(this=key, desc=ordered.args.get("desc"), nulls_first=ordered.args.get("nulls_first")))

    inner = tree.copy()
    inner.set("order", None)
    inner.set("limit", None)
    rank = exp.Window(this=exp.Anonymous(this="RANK"), order=exp.Order(expressions=keys))
    inner = inner.select(exp.alias_(rank, RANK_COLUMN), copy=False)
    outer = (exp.select("*").from_(inner.subquery("top_n"))
             .where(exp.LTE(this=exp.column(RANK_COLUMN), expression=exp.Literal.number(n)))
             .order_by(exp.column(RANK_COLUMN)))
    return outer.sql(dialect=dialect), n
