"""Synthea data preparation: which table goes to which database, and how CSVs are cleaned."""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.types import String

from app.data import synthea
from app.data.synthea import PATIENT_COLUMN, TABLE_SPLIT, download_synthea, load_table, sql_dtypes

FIXTURES = Path(__file__).parent / "fixtures" / "mini_synthea"


def test_split_covers_all_18_tables():
    assert len(TABLE_SPLIT) == 18
    assert sum(1 for v in TABLE_SPLIT.values() if v == "clinical") == 12
    assert sum(1 for v in TABLE_SPLIT.values() if v == "billing") == 6
    assert TABLE_SPLIT["observations"] == "clinical"
    assert TABLE_SPLIT["claims_transactions"] == "billing"


def test_patient_column_map():
    assert PATIENT_COLUMN["patients"] == "id"
    assert PATIENT_COLUMN["claims"] == "patientid"
    assert PATIENT_COLUMN["claims_transactions"] == "patientid"
    assert PATIENT_COLUMN["encounters"] == "patient"
    assert PATIENT_COLUMN["payer_transitions"] == "patient"
    for reference_table in ("providers", "organizations", "payers"):
        assert reference_table not in PATIENT_COLUMN


def test_load_table_lowercases_and_parses_dates():
    df = load_table(FIXTURES / "encounters.csv")
    assert "start" in df.columns and "START" not in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["start"])
    patients = load_table(FIXTURES / "patients.csv")
    assert pd.api.types.is_datetime64_any_dtype(patients["birthdate"])


def test_sql_dtypes_id_columns_are_varchar64():
    df = load_table(FIXTURES / "claims.csv")
    dtypes = sql_dtypes(df)
    for col in ("id", "patientid", "providerid", "appointmentid"):
        assert isinstance(dtypes[col], String) and dtypes[col].length == 64
    assert "diagnosis1" not in dtypes  # ordinary columns are left to pandas
    assert "departmentid" not in dtypes  # numeric ids stay numbers


def test_download_skips_when_present(tmp_path, monkeypatch):
    folder = tmp_path / "synthea"
    folder.mkdir()
    (folder / "patients.csv").write_text("Id\n1\n")

    def boom(*args, **kwargs):
        raise AssertionError("network must not be used when data already exists")

    monkeypatch.setattr(synthea.httpx, "stream", boom)
    assert download_synthea(tmp_path) == folder
