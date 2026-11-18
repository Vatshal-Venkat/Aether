"""The question set itself: loads, ids unique, every case is scoreable, gold SQL parses."""

import sqlglot

from app.eval.cases import QUESTIONS_PATH, load_cases


def test_question_set_loads_and_is_scoreable():
    cases = load_cases(QUESTIONS_PATH)
    assert len(cases) >= 40
    assert len({c.id for c in cases}) == len(cases)
    for c in cases:
        if c.planned:
            continue
        assert c.gold or c.must_contain or c.privacy or c.expect_kind != "answer", f"{c.id} has no way to be scored"


def test_gold_sql_parses_in_its_dialect():
    for c in load_cases(QUESTIONS_PATH):
        if c.gold:
            dialect = "postgres" if c.gold.db == "clinical" else "mysql"
            assert sqlglot.parse_one(c.gold.sql.replace(":patient_id", "'x'"), read=dialect), c.id


def test_every_category_present():
    cats = {c.category for c in load_cases(QUESTIONS_PATH)}
    assert {"clinical", "billing", "cross_db", "rag", "hybrid", "patient", "privacy", "safety", "conversation"} <= cats
