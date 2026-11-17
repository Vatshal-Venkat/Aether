"""Synthea data: download it, decide where each table lives, and tidy each CSV.

Plain English: Synthea gives us 18 spreadsheets (CSV files) of fake patients. This module
1) fetches them if they aren't on disk yet, 2) says which database each one belongs in
(medical record -> PostgreSQL, billing -> MySQL), and 3) cleans them up: lower-case
column names (easier for the AI to write correct SQL), real dates instead of text, and
fixed-length text for ID columns (MySQL needs that to index them).
"""

import zipfile
from pathlib import Path
from typing import Literal

import httpx
import pandas as pd
from sqlalchemy.types import Date, String, TypeEngine

SYNTHEA_URL = (
    "https://synthetichealth.github.io/synthea-sample-data/downloads/latest/synthea_sample_data_csv_latest.zip"
)

# Which database each Synthea table goes to.
TABLE_SPLIT: dict[str, Literal["clinical", "billing"]] = {
    # Medical record -> PostgreSQL clinical_db
    "patients": "clinical",
    "encounters": "clinical",
    "conditions": "clinical",
    "observations": "clinical",
    "medications": "clinical",
    "procedures": "clinical",
    "immunizations": "clinical",
    "allergies": "clinical",
    "careplans": "clinical",
    "devices": "clinical",
    "imaging_studies": "clinical",
    "supplies": "clinical",
    # Business side -> MySQL billing_db
    "organizations": "billing",
    "providers": "billing",
    "payers": "billing",
    "payer_transitions": "billing",
    "claims": "billing",
    "claims_transactions": "billing",
}

# For each table that holds patient data: the column containing the patient's id.
# Used for privacy filtering (a patient may only see rows where this column = their id).
# Reference tables (providers, organizations, payers) are absent on purpose.
PATIENT_COLUMN: dict[str, str] = {
    "patients": "id",
    "claims": "patientid",
    "claims_transactions": "patientid",
    **{
        t: "patient"
        for t in (
            "encounters", "conditions", "observations", "medications", "procedures", "immunizations",
            "allergies", "careplans", "devices", "imaging_studies", "supplies", "payer_transitions",
        )
    },
}

ID_COLUMNS = {
    "id", "patient", "patientid", "encounter", "provider", "providerid",
    "organization", "payer", "claimid", "chargeid",
}

DATE_COLUMNS = {
    "start", "stop", "date", "birthdate", "deathdate", "servicedate", "currentillnessdate",
    "lastbilleddate1", "lastbilleddate2", "lastbilleddatep", "fromdate", "todate", "start_date", "end_date",
}


def _find_csv_folder(root: Path) -> Path | None:
    hit = next(root.rglob("patients.csv"), None) if root.exists() else None
    return hit.parent if hit else None


def download_synthea(dest_dir: Path) -> Path:
    """Return the folder holding the Synthea CSVs, downloading + unzipping only if needed."""
    existing = _find_csv_folder(dest_dir)
    if existing:
        return existing
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "synthea.zip"
    with httpx.stream("GET", SYNTHEA_URL, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with zip_path.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir / "synthea")
    zip_path.unlink()
    folder = _find_csv_folder(dest_dir)
    if folder is None:
        raise RuntimeError("Downloaded Synthea archive did not contain patients.csv")
    return folder


def load_table(csv_path: Path) -> pd.DataFrame:
    """Read one Synthea CSV: lower-case column names and turn date columns into real dates."""
    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = [c.lower() for c in df.columns]
    for col in DATE_COLUMNS & set(df.columns):
        raw = df[col].dropna().astype(str)
        parsed = pd.to_datetime(df[col], utc=True, format="ISO8601", errors="coerce")
        if len(raw) and (raw.str.len() == 10).all():
            # Calendar dates like "1985-03-21" (birthdate) stay plain dates — no time, no time zone.
            df[col] = parsed.dt.date.astype(object).where(parsed.notna(), None)
        else:
            df[col] = parsed  # real moments in time, e.g. "2017-02-22T04:27:13Z"
    return df


def _is_id_column(name: str) -> bool:
    return name in ID_COLUMNS or name.endswith("id")


def sql_dtypes(df: pd.DataFrame) -> dict[str, TypeEngine]:
    """Column types to force when creating the SQL table: text ID columns become VARCHAR(64).

    Numeric ids (e.g. departmentid) are left as numbers.
    """
    types: dict[str, TypeEngine] = {
        col: String(64)
        for col in df.columns
        if _is_id_column(col) and not pd.api.types.is_numeric_dtype(df[col])
    }
    for col in DATE_COLUMNS & set(df.columns):
        if df[col].dtype == object:  # plain calendar dates (see load_table)
            types[col] = Date()
    return types
