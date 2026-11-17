"""The number checker — catches numbers the AI made up.

Plain English: after the AI writes an answer, we find every number in it and check that
each one really came from the query results (or from the question itself, or a simple
count like "3 rows"). Rounding is allowed ("12.35" for 12.3456), so is formatting
("$1,234.5", "45%" for 0.45), and dates the AI rewrote in words. Digits glued to letters
(Synthea names like "Abe604") and list numbering ("1.", "2.") are ignored.
Anything left over is reported, so we can ask the AI to fix it or warn the user.
"""

import re
from typing import Any

# A number not glued to letters/digits: optional $, digits with optional thousands commas, decimals, optional %.
NUMBER = re.compile(r"(?<![A-Za-z0-9_.])(\$?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(%?)(?![A-Za-z0-9_])")
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s+")
ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")


def _numbers_in_text(text: str) -> set[float]:
    return {float(m.group(2).replace(",", "") + (m.group(3) or "")) for m in NUMBER.finditer(text)}


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
    for a in allowed:
        if abs(a - value) < 1e-9 or round(a, decimals) == value:
            return True
        if percent and round(a * 100, decimals) == value:
            return True
    return False


def find_unverified_numbers(answer: str, rows: list[list[Any]], question: str, extra_allowed: set[float]) -> list[str]:
    allowed = _allowed_numbers(rows, question, extra_allowed)
    text = LIST_MARKER.sub("", answer)
    bad = []
    for m in NUMBER.finditer(text):
        dollar, whole, frac, pct = m.groups()
        value = float(whole.replace(",", "") + (frac or ""))
        decimals = len(frac) - 1 if frac else 0
        if not _matches(value, decimals, bool(pct), allowed):
            bad.append(m.group(0))
    return bad
