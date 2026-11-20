"""Rows are not patients — say how many different patients a result covers, and catch "N patients" when N is rows.

Plain English: live (2026-11-20), "How many patients have diabetes?" said 8. The follow-up "show their names"
returned one row per patient PER diabetes-related diagnosis (diabetes, kidney disease, neuropathy...): 19 rows for the
same 8 people. The answer said "19 patients". Same filter, wrong unit, and the number check couldn't see it (19 is
in the data).

  * distinct_note(): if a result has a patient column (patient_id / patient / patientid, or first + last name) and
    patients repeat, the answer-writer is told "these 19 rows cover only 8 different patients";
  * wrong_patient_counts(): after the answer is written, "19 patients" when 19 is the number of ROWS but the rows
    hold a different number of patients is flagged (rewrite once, then a visible warning).
"""

import re

from app.graph.state import QueryResult

PATIENT_ID = re.compile(r"^(patient|patient_?id|patientid)$", re.IGNORECASE)
FULL_NAME = re.compile(r"^(full_?name|patient_?name|name)$", re.IGNORECASE)
PATIENTS = re.compile(r"(?<![\w.,])(\d[\d,]*)\s+(?:different\s+|distinct\s+|unique\s+|individual\s+)?patients?\b",
                      re.IGNORECASE)


def _patient_key(result: QueryResult) -> tuple[str, list[int]] | None:
    """Which column(s) say who a row is about: an id column first, else first + last names, else a full name."""
    cols = [c.lower() for c in result.columns]
    ids = [i for i, c in enumerate(result.columns) if PATIENT_ID.match(c)]
    if ids:
        return result.columns[ids[0]], ids[:1]
    if "first" in cols and "last" in cols:
        return "first + last", [cols.index("first"), cols.index("last")]
    names = [i for i, c in enumerate(result.columns) if FULL_NAME.match(c) and c.lower() != "name"]
    return (result.columns[names[0]], names[:1]) if names else None


def _counts(result: QueryResult) -> tuple[str, int, int] | None:
    """(key column, rows, different patients) — only when some patient appears more than once."""
    key = _patient_key(result)
    if key is None or len(result.rows) < 2:
        return None
    label, idx = key
    different = len({tuple(row[i] for i in idx) for row in result.rows})
    return (label, len(result.rows), different) if different < len(result.rows) else None


def different_patients(result: QueryResult | None) -> int | None:
    """How many different patients the rows hold, when that differs from the row count (else None)."""
    found = _counts(result) if result is not None else None
    return found[2] if found else None


def distinct_note(result: QueryResult) -> str | None:
    found = _counts(result)
    if found is None:
        return None
    label, rows, different = found
    scope = " (of the rows kept; the result was cut off)" if result.truncated else ""
    return (f"Note: these {rows} rows cover only {different} different patients (by {label}){scope}: some patients "
            f"appear on several rows (e.g. one row per diagnosis or visit). When you count patients, say {different}, "
            f"not {rows}; list each patient once.")


def wrong_patient_counts(answer: str, result: QueryResult | None) -> list[str]:
    """'19 patients' when 19 is the number of rows, not of patients -> ['19 patients (the 19 rows cover 8 ...)']."""
    if result is None or (found := _counts(result)) is None:
        return []
    _, rows, different = found
    wrong = []
    for m in PATIENTS.finditer(answer):
        n = int(m.group(1).replace(",", ""))
        if n in (rows, result.total_rows) and n != different:
            note = f"{m.group(1)} patients (the {rows} rows cover {different} different patients)"
            if note not in wrong:
                wrong.append(note)
    return wrong
