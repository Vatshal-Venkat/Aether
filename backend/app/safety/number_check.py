"""The number checker — catches numbers the AI made up.

Plain English: after the AI writes an answer, we find every number in it and check that
each one really came from the query results (or from the question itself, or a simple
count like "3 rows"). Rounding is allowed ("12.35" for 12.3456), so is formatting
("$1,234.5", "45%" for 0.45), and dates the AI rewrote in words. Digits glued to letters
(Synthea names like "Abe604"), list numbering ("1.", "2.") and a "Rank" column in an answer table are ignored.
Signs count: "-20,451.57" must match a negative value (a minus written as -, − or – and attached to the
number; "2019-2021" is a range, not a negative). A negative value may also be described without its sign
("a credit of 20,451.57").
Anything left over is reported, so we can ask the AI to fix it or warn the user.
"""

import re
from typing import Any

# A number not glued to letters/digits: optional minus attached to it, optional $, digits with optional
# thousands commas, decimals, optional %.
NUMBER = re.compile(r"(?<![A-Za-z0-9_.])([-−–]?)(\$?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)(?![A-Za-z0-9_])")
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s+")
ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")
RANK_HEADER = re.compile(r"^\s*(rank|#|no\.?|position|pos\.?|place)\s*$", re.IGNORECASE)
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _value(m: re.Match) -> float:
    sign, _dollar, whole, frac, _pct = m.groups()
    value = float(whole.replace(",", "") + (frac or ""))
    return -value if sign else value


def _numbers_in_text(text: str) -> set[float]:
    return {_value(m) for m in NUMBER.finditer(text)}


def _cells(line: str) -> list[str]:
    return line.strip().strip("|").split("|")


def _drop_rank_columns(text: str) -> str:
    """Blank the cells of a "Rank" / "#" column in markdown tables: positions the AI numbered, not data."""
    lines = text.split("\n")
    rank_cols: set[int] = set()
    for i, line in enumerate(lines):
        if "|" not in line:
            rank_cols = set()
            continue
        if i + 1 < len(lines) and TABLE_RULE.match(lines[i + 1]) and not TABLE_RULE.match(line):
            rank_cols = {j for j, cell in enumerate(_cells(line)) if RANK_HEADER.match(cell)}  # a header row
        elif rank_cols and not TABLE_RULE.match(line):
            cells = _cells(line)
            lines[i] = "|" + "|".join("" if j in rank_cols else c for j, c in enumerate(cells)) + "|"
    return "\n".join(lines)


def _allowed_numbers(rows: list[list[Any]], question: str, extra: set[float]) -> set[float]:
    allowed = set(extra) | _numbers_in_text(question)
    for row in rows:
        for cell in row:
            if isinstance(cell, bool) or cell is None:
                continue
            if isinstance(cell, (int, float)):
                allowed.add(float(cell))
            elif isinstance(cell, str):
                date = ISO_DATE.match(cell)
                if date:
                    allowed |= {float(g) for g in date.groups() if g}
                else:
                    allowed |= _numbers_in_text(cell)
    return allowed


def _matches(value: float, decimals: int, percent: bool, allowed: set[float]) -> bool:
    if value >= 0:  # written without a sign: a negative value described in words ("a credit of 20.5") is fine
        allowed = allowed | {abs(a) for a in allowed}
    for a in allowed:
        if abs(a - value) < 1e-9 or round(a, decimals) == value:
            return True
        if percent and round(a * 100, decimals) == value:
            return True
    return False


# Numbers written as words are checked too ("Four patients..."). "one" is left out on purpose:
# it is far more often prose ("no one", "one of them") than a count.
NUMBER_WORDS = {
    w: i for i, w in enumerate(
        "zero _ two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    ) if w != "_"
}
WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def find_unverified_numbers(answer: str, rows: list[list[Any]], question: str, extra_allowed: set[float]) -> list[str]:
    allowed = _allowed_numbers(rows, question, extra_allowed)
    text = LIST_MARKER.sub("", _drop_rank_columns(answer))
    # Number words that are part of the data or question (a doctor called "Dr Two") are not counts.
    quoted_words = {w.lower() for cell in [question, *(c for r in rows for c in r if isinstance(c, str))]
                    for w in WORD.findall(cell)}
    bad = [m.group(0) for m in WORD.finditer(text)
           if m.group(0).lower() not in quoted_words
           and not _matches(float(NUMBER_WORDS[m.group(0).lower()]), 0, False, allowed)]
    for m in NUMBER.finditer(text):
        _sign, _dollar, _whole, frac, pct = m.groups()
        value = _value(m)
        decimals = len(frac) - 1 if frac else 0
        if not _matches(value, decimals, bool(pct), allowed):
            bad.append(m.group(0))
    return bad
