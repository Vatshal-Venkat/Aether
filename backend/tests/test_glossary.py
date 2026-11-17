"""The glossary: our tiny "semantic layer" — plain meanings for tables, columns and business terms."""

from app.data.synthea import TABLE_SPLIT
from app.semantic.glossary import load_glossary


def test_glossary_loads():
    g = load_glossary()
    assert g.terms, "glossary should define business terms"
    hba1c = next(t for t in g.terms if t.term.lower() == "hba1c")
    assert hba1c.db == "clinical"
    assert "a1c" in hba1c.sql_hint.lower()


def test_glossary_tables_match_split():
    assert set(load_glossary().tables) == set(TABLE_SPLIT)


def test_glossary_pii_list():
    assert set(load_glossary().pii_columns) == {"patients.ssn", "patients.drivers", "patients.passport"}


def test_glossary_columns_reference_known_tables():
    for key in load_glossary().columns:
        table, _, column = key.partition(".")
        assert table in TABLE_SPLIT and column, key
