"""Merging step 1's and step 2's results on the link column (a left join done in Python)."""

from app.graph.nodes.merge import merge_results
from app.graph.state import QueryResult


def qr(columns, rows, truncated=False):
    return QueryResult(columns=columns, rows=rows, total_rows=len(rows), truncated=truncated)


LEFT = qr(["provider", "n"], [["d2", 9], ["d1", 5], ["d9", 1]])
RIGHT = qr(["id", "name"], [["d1", "Dr One"], ["d2", "Dr Two"]])


def test_left_join_keeps_left_order():
    out = merge_results(LEFT, RIGHT, "provider", "id", cap=1000)
    assert out.columns == ["provider", "n", "name"]
    assert out.rows[:2] == [["d2", 9, "Dr Two"], ["d1", 5, "Dr One"]]


def test_unmatched_left_rows_get_nulls():
    assert merge_results(LEFT, RIGHT, "provider", "id", cap=1000).rows[2] == ["d9", 1, None]


def test_key_match_is_case_insensitive_on_column_names():
    out = merge_results(qr(["PROVIDER", "n"], [["d1", 5]]), qr(["ID", "name"], [["d1", "Dr One"]]), "provider", "id", 1000)
    assert out.rows == [["d1", 5, "Dr One"]]


def test_clash_suffix():
    right = qr(["id", "n"], [["d1", 77]])
    out = merge_results(qr(["provider", "n"], [["d1", 5]]), right, "provider", "id", cap=1000)
    assert out.columns == ["provider", "n", "n_2"] and out.rows == [["d1", 5, 77]]


def test_one_left_row_many_right_rows():
    right = qr(["patientid", "claim"], [["p1", "c1"], ["p1", "c2"]])
    out = merge_results(qr(["id", "first"], [["p1", "Ann"]]), right, "id", "patientid", cap=1000)
    assert out.rows == [["p1", "Ann", "c1"], ["p1", "Ann", "c2"]]


def test_right_without_key_is_returned():
    total = qr(["owed"], [[123.5]])
    assert merge_results(LEFT, total, "provider", "id", cap=1000) == total


def test_cap_and_truncation():
    out = merge_results(LEFT, RIGHT, "provider", "id", cap=2)
    assert out.total_rows == 2 and out.truncated
    assert merge_results(qr(["provider"], [["d1"]], truncated=True), RIGHT, "provider", "id", 1000).truncated


def test_single_rows_kept_side_by_side_when_no_key():
    # Live test C9: step 1 total (visits) + step 2 total (claims) -> keep both so the answer can state both.
    out = merge_results(qr(["id", "visits_paid"], [["p1", 160191.0]]), qr(["claims_paid"], [[144482.55]]), "id", "patientid", 1000)
    assert out.columns == ["id", "visits_paid", "claims_paid"] and out.rows == [["p1", 160191.0, 144482.55]]


def test_truncated_step1_marks_aggregate_partial():
    # Final review: step 1 cut at the cap + step 2 total -> the total must be flagged partial.
    out = merge_results(qr(["id"], [["p1"], ["p2"]], truncated=True), qr(["owed"], [[10.0]]), "id", "patientid", 1000)
    assert out.rows == [[10.0]] and out.truncated
