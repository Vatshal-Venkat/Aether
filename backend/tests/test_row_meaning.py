"""Rows are not patients: "19 rows" of diagnoses can be only 8 different people.

Live (2026-11-20): "How many patients have diabetes?" -> 8. Follow-up "show their names" returned one row per patient
per diabetes-related diagnosis (19 rows, 8 people) and the answer said "19 patients". Same filter, wrong unit."""

from app.graph.state import QueryResult
from app.safety.row_meaning import distinct_note, wrong_patient_counts

KENDRICK, MIRANDA, ANGELYN = "p-k", "p-m", "p-a"
ROWS = ([[KENDRICK, "Kendrick Oberbrunner", d] for d in ["Diabetes", "Kidney", "Neuropathy", "Microalbuminuria", "Proteinuria"]]
        + [[MIRANDA, "Miranda Jacobs", d] for d in ["Diabetes", "Kidney"]]
        + [[ANGELYN, "Angelyn Harris", "Diabetes"]])
DIAGNOSES = QueryResult(columns=["patient_id", "full_name", "condition"], rows=ROWS, total_rows=8, truncated=False)
ONE_EACH = QueryResult(columns=["patient_id", "full_name"], rows=[[KENDRICK, "K"], [MIRANDA, "M"]], total_rows=2,
                       truncated=False)


def test_note_says_how_many_different_patients_the_rows_cover():
    note = distinct_note(DIAGNOSES)
    assert "8 rows" in note and "3 different patients" in note and "patient_id" in note


def test_no_note_when_every_row_is_a_different_patient_or_there_is_no_patient_column():
    assert distinct_note(ONE_EACH) is None
    assert distinct_note(QueryResult(columns=["name", "n"], rows=[["a", 1], ["a", 2]], total_rows=2, truncated=False)) is None


def test_names_count_when_there_is_no_id_column():
    t = QueryResult(columns=["first", "last", "condition"], rows=[["Ann", "Lee", "x"], ["Ann", "Lee", "y"], ["Bob", "Ray", "x"]],
                    total_rows=3, truncated=False)
    assert "2 different patients" in distinct_note(t)


def test_calling_rows_patients_is_caught():
    assert wrong_patient_counts("The query identified 8 patients with diabetes.", DIAGNOSES) == [
        "8 patients (the 8 rows cover 3 different patients)"]
    assert wrong_patient_counts("3 patients have a diabetes-related diagnosis (8 diagnoses).", DIAGNOSES) == []
    assert wrong_patient_counts("There are 2 patients.", ONE_EACH) == []
