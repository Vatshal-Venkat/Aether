"""Highest / lowest worked out by code — and claims like "a peak of 382" checked against the whole table.

Live (2026-11-20): "How many visits were there each year since 2010?" returned 17 rows. The AI was shown only the
first 10 (2010-2019) and wrote "a peak of 382 visits in 2018" — but 2021 had 502. Every number was real, so the
number check passed; the CLAIM was wrong."""

from app.graph.state import QueryResult
from app.safety.extremes import extremes_note, wrong_extremes

VISITS = [[2010, 31], [2011, 47], [2012, 49], [2013, 82], [2014, 67], [2015, 50], [2016, 135], [2017, 330],
          [2018, 382], [2019, 330], [2020, 357], [2021, 502], [2022, 412], [2023, 367], [2024, 410], [2025, 344],
          [2026, 366]]


def table(columns, rows, truncated=False):
    return QueryResult(columns=columns, rows=rows, total_rows=len(rows), truncated=truncated)


YEARS = table(["year", "visits"], VISITS)
INSURERS = table(["name", "customers"], [["Medicaid", 52], ["NO_INSURANCE", 46], ["Aetna", 26], ["Humana", 21]])


def test_note_gives_highest_lowest_first_and_last_over_all_rows():
    note = extremes_note(YEARS)
    assert "all 17 rows" in note
    assert "highest 502 (year 2021)" in note and "lowest 31 (year 2010)" in note
    assert "first 31 (year 2010)" in note and "last 366 (year 2026)" in note


def test_note_lists_ties_and_skips_ids_and_ranks():
    t = table(["patient_id", "name", "ranking", "n"], [["a", "Ann", 1, 5], ["b", "Bob", 1, 5], ["c", "Cy", 3, 2]])
    note = extremes_note(t)
    assert "highest 5 (name Ann, Bob)" in note
    assert "ranking" not in note and "patient_id" not in note


def test_note_says_when_the_result_was_cut_off():
    assert "rows kept" in extremes_note(table(["year", "visits"], VISITS, truncated=True))


def test_no_note_without_a_measure_or_with_one_row():
    assert extremes_note(table(["first", "last"], [["Ann", "Lee"], ["Bob", "Ray"]])) is None
    assert extremes_note(table(["n"], [[8]])) is None


def test_a_wrong_peak_is_caught():
    answer = "Visits rose from 31 in 2010 to a peak of 382 visits in 2018, then fell to 330 in 2019."
    assert wrong_extremes(answer, YEARS) == ["382 (called the highest; the highest visits is 502)"]


def test_a_wrong_lowest_is_caught():
    assert wrong_extremes("The lowest year was 2011 with 47 visits.", YEARS) == [
        "47 (called the lowest; the lowest visits is 31)"]


def test_right_claims_pass():
    assert wrong_extremes("Visits peaked at 502 in 2021; the lowest was 31 in 2010.", YEARS) == []
    assert wrong_extremes("Medicaid has the most customers (52); Humana has the fewest, 21.", INSURERS) == []


def test_plain_numbers_and_ordinary_words_are_not_claims():
    assert wrong_extremes("Most patients visited in 2017 (330 visits).", YEARS) == []  # "most" as in "most patients"
    assert wrong_extremes("There were 382 visits in 2018.", YEARS) == []


def test_tables_with_repeated_labels_are_not_judged():
    # "highest for women" may rightly be below the overall highest when each year has two rows.
    t = table(["year", "gender", "visits"], [[2020, "F", 300], [2020, "M", 500], [2021, "F", 200]])
    assert wrong_extremes("The highest for women was 300 in 2020.", t) == []
