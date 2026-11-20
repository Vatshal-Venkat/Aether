"""Highest and lowest, worked out by code — and "peak / highest / lowest" claims checked against the whole table.

Plain English: for a long result the AI is shown only the first 10 rows (to keep answers short and fast). Live
(2026-11-20), "visits each year since 2010" had 17 rows; the AI saw 2010-2019 and wrote "a peak of 382 visits in
2018" — but 2021 had 502. Every number in that sentence was real, so the number check passed; the CLAIM was wrong.

Two fixes:
  * extremes_note(): when the AI sees only part of a table, code computes the highest and lowest value of each
    amount column (and the first and last, for years and dates) over ALL rows, and the AI is told to use those;
  * wrong_extremes(): after the answer is written, a sentence that calls a number the peak / highest / lowest is
    checked against the whole table. A wrong one gets the answer rewritten once, then a visible warning.

Amount columns are number columns that aren't ids, codes, ranks or years. Tables where a label repeats (e.g. one row
per year AND gender) are not judged: "the highest for women" may rightly be below the overall highest.
"""

import re

from app.graph.state import QueryResult

ID_NAME = re.compile(r"(^|_)(id|uuid)$|^id$|code$", re.IGNORECASE)
RANK_NAME = re.compile(r"^(rank|ranking|row_?num(ber)?|position)$", re.IGNORECASE)
DATE_TEXT = re.compile(r"^\d{4}(-\d{2}(-\d{2}([T ][\d:.]+Z?)?)?)?$")
HIGH = re.compile(r"\b(peak(?:ed|s)?|highest|maximum|largest|biggest|greatest|the most)\b", re.IGNORECASE)
LOW = re.compile(r"\b(lowest|minimum|smallest|fewest|the least)\b", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?![\w])")
SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")
NEAR = 80  # characters after (or before) the word in which the claimed number must appear
MAX_LABELS = 3


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(round(float(v), 4))


def _is_year(name: str, values: list) -> bool:
    return "year" in name.lower() and all(_is_number(v) and float(v).is_integer() and 1800 <= v <= 2200 for v in values)


def _layout(result: QueryResult) -> tuple[int | None, list[int], bool]:
    """(label column, amount columns, labels are years/dates)."""
    cols = result.columns
    values = [[r[i] for r in result.rows if r[i] is not None] for i in range(len(cols))]
    numeric = [bool(v) and all(_is_number(x) for x in v) for v in values]
    years = [numeric[i] and _is_year(c, values[i]) for i, c in enumerate(cols)]
    label = next((i for i, c in enumerate(cols) if not numeric[i] and not ID_NAME.search(c)), None)
    if label is None:
        label = next((i for i, y in enumerate(years) if y), None)
    measures = [i for i, c in enumerate(cols) if numeric[i] and not years[i] and i != label
                and not ID_NAME.search(c) and not RANK_NAME.match(c)]
    timeline = label is not None and (years[label] or all(isinstance(v, str) and DATE_TEXT.match(v.strip())
                                                          for v in values[label]))
    return label, measures, bool(timeline)


def _labels_of(result: QueryResult, label: int | None, col: int, value: float) -> str:
    if label is None:
        return ""
    names = [str(r[label]) for r in result.rows if r[col] == value]
    shown = ", ".join(names[:MAX_LABELS]) + (f" and {len(names) - MAX_LABELS} more" if len(names) > MAX_LABELS else "")
    return f" ({result.columns[label]} {shown})"


def extremes_note(result: QueryResult) -> str | None:
    """'Computed by code over all 17 rows: visits — highest 502 (year 2021), lowest 31 (year 2010), ...'."""
    if len(result.rows) < 2:
        return None
    label, measures, timeline = _layout(result)
    if not measures:
        return None
    parts = []
    for c in measures:
        vals = [r[c] for r in result.rows if r[c] is not None]
        if not vals:
            continue
        hi, lo = max(vals), min(vals)
        facts = [f"highest {_fmt(hi)}{_labels_of(result, label, c, hi)}", f"lowest {_fmt(lo)}{_labels_of(result, label, c, lo)}"]
        if timeline:
            first, last = result.rows[0], result.rows[-1]
            facts += [f"first {_fmt(first[c])} ({result.columns[label]} {first[label]})",
                      f"last {_fmt(last[c])} ({result.columns[label]} {last[label]})"]
        parts.append(f"{result.columns[c]} — {', '.join(facts)}")
    if not parts:
        return None
    scope = (f"the {len(result.rows)} rows kept (the result was cut off)" if result.truncated
             else f"all {len(result.rows)} rows")
    return f"Computed by code over {scope}: " + "; ".join(parts) + "."


def _claimed(text: str, result: QueryResult, measures: list[int]) -> tuple[str, int, float] | None:
    """The first number in `text` that is a value of exactly one amount column: (as written, column, value)."""
    for m in NUMBER.finditer(text):
        try:
            value = float(m.group().replace(",", ""))
        except ValueError:
            continue
        cols = [c for c in measures if any(r[c] is not None and abs(r[c] - value) < 0.005 for r in result.rows)]
        if len(cols) == 1:
            return m.group(), cols[0], value
    return None


def wrong_extremes(answer: str, result: QueryResult | None) -> list[str]:
    """Numbers the answer calls the peak / highest / lowest that aren't, e.g. '382 (called the highest; ...)'."""
    if result is None or len(result.rows) < 2:
        return []
    label, measures, _ = _layout(result)
    if label is None or not measures:
        return []
    labels = [r[label] for r in result.rows]
    if len(set(map(str, labels))) != len(labels):
        return []  # repeated labels: a "highest" may be about one group, not the whole table
    wrong: list[str] = []
    for sentence in SENTENCE.split(answer):
        for pattern, word, pick in ((HIGH, "highest", max), (LOW, "lowest", min)):
            for m in pattern.finditer(sentence):
                after = sentence[m.end():m.end() + NEAR]
                before = sentence[max(0, m.start() - NEAR):m.start()]
                found = _claimed(after, result, measures)
                if found is None:  # "... 382 visits, the highest": the number comes first
                    hits = [h for h in (_claimed(x.group(), result, measures) for x in NUMBER.finditer(before)) if h]
                    found = hits[-1] if hits else None
                if found is None:
                    continue
                written, col, value = found
                target = pick(r[col] for r in result.rows if r[col] is not None)
                if abs(value - target) >= 0.005:
                    note = f"{written} (called the {word}; the {word} {result.columns[col]} is {_fmt(target)})"
                    if note not in wrong:
                        wrong.append(note)
    return wrong
