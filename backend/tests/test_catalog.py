"""Schema catalog: the list of tables/columns the AI is allowed to see (PII removed)."""

import pytest
from sqlalchemy import create_engine, text

from app.db.catalog import build_catalog
from app.semantic.glossary import Glossary


@pytest.fixture
def catalog():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, ssn TEXT, birthdate TIMESTAMP)"))
        conn.execute(text("CREATE TABLE conditions (patient TEXT, description TEXT, stop TIMESTAMP)"))
        conn.execute(text("CREATE TABLE scratch_unknown (x INT)"))  # not in glossary -> ignored
    glossary = Glossary(
        tables={"patients": "One row per person.", "conditions": "Diagnoses."},
        columns={"conditions.stop": "NULL means the condition is ongoing."},
        terms=[],
        pii_columns=["patients.ssn"],
        join_keys=[],
    )
    return build_catalog({"clinical": engine}, glossary)


def test_catalog_drops_pii(catalog):
    cols = [c.name for c in catalog.tables["patients"].columns]
    assert "ssn" not in cols and "first" in cols
    assert "ssn" not in catalog.render(["patients"])


def test_render_includes_descriptions(catalog):
    out = catalog.render(["conditions"])
    assert "Diagnoses." in out
    assert "NULL means the condition is ongoing." in out


def test_category_values_shown_to_ai():
    # Live test bug: the AI guessed gender = 'female' but the data stores 'F' -> confident "0".
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, gender TEXT, first TEXT, ssn TEXT)"))
        for i in range(30):
            conn.execute(text("INSERT INTO patients VALUES (:i, :g, :f, '999-00-0000')"),
                         {"i": f"id-{i}", "g": "F" if i % 2 else "M", "f": f"Name{i}"})
    g = Glossary(tables={"patients": "People."}, columns={}, terms=[], pii_columns=["patients.ssn"], join_keys=[])
    rendered = build_catalog({"clinical": engine}, g).render(["patients"])
    assert "values: 'F', 'M'" in rendered          # short category column: values listed
    assert "Name1" not in rendered                  # many distinct values (names): not listed
    assert "id-1" not in rendered                   # id columns: never listed
    assert "999-00-0000" not in rendered            # PII: never listed


def test_allowed_tables(catalog):
    assert catalog.allowed_tables("clinical") == {"patients", "conditions"}
    assert [t.name for t in catalog.for_db("clinical")] == ["conditions", "patients"]


def test_render_hides_columns(catalog):
    out = catalog.render(["patients"], hidden={"patients.first"})
    assert "first" not in out and "birthdate" in out
