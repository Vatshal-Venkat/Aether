"""Number check: every number in an answer must come from the query results (or the question)."""

from app.safety.number_check import find_unverified_numbers


def check(answer, rows, question="", extra=frozenset()):
    return find_unverified_numbers(answer, rows, question, set(extra))


def test_exact_match():
    assert check("There are 111 patients.", [[111]]) == []


def test_thousands_separator():
    assert check("Total spend was $1,234.5.", [[1234.5]]) == []


def test_rounding():
    assert check("Average HbA1c is 12.35%.", [[12.3456]]) == []
    assert check("Average is about 12.", [[12.3456]]) == []


def test_percent():
    assert check("45% of visits were wellness visits.", [[0.45]]) == []


def test_row_count_allowed():
    assert check("I found 3 matching medications.", [["a"], ["b"], ["c"]], extra={3}) == []


def test_question_numbers_allowed():
    assert check("Visits in 2019: 4.", [[4]], question="How many visits in 2019?") == []


def test_names_ignored():
    assert check("Abe604 Bode78 has 3 visits.", [["Abe604", 3]]) == []


def test_numbers_inside_text_cells_allowed():
    assert check("Metformin 500 MG oral tablet.", [["metformin hydrochloride 500 MG Oral Tablet"]]) == []


def test_dates_reformatted_from_cells_allowed():
    assert check("The last visit was on 17 February 2019.", [["2019-02-17T05:07:38+00:00"]]) == []


def test_numbered_list_markers_ignored():
    assert check("Top conditions:\n1. Gingivitis (40)\n2. Anemia (12)", [["Gingivitis", 40], ["Anemia", 12]]) == []


def test_invented_number_flagged():
    assert check("Abe604 has 7 visits.", [["Abe604", 3]]) == ["7"]


def test_number_words_are_checked_too():
    # Live test: the AI wrote "Four patients..." — words must be checked like digits.
    assert check("Four patients have a peanut allergy.", [[4]]) == []
    assert check("Five patients have a peanut allergy.", [[4]]) == ["Five"]
    assert check("Zero patients have Ebola.", [[0]]) == []


def test_invented_money_flagged():
    assert check("Insurance paid $9,999.00 in total.", [[120.0]]) == ["$9,999.00"]
