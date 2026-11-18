"""The glossary: our tiny "semantic layer" — plain meanings for tables, columns and business terms."""

from app.data.synthea import TABLE_SPLIT
from app.semantic.glossary import load_glossary


def test_glossary_loads():
    g = load_glossary()
    assert g.terms, "glossary should define business terms"
    hba1c = next(t for t in g.terms if t.term.lower() == "hba1c")
    assert hba1c.db == "clinical"
    assert "a1c" in hba1c.sql_hint.lower()


def test_name_hints_cover_names_typed_without_digits():
    # The website shows "Abe Bode" (no Synthea digits), so people type it that way: the AI must match with LIKE.
    cols = load_glossary().columns
    for key in ("patients.first", "patients.last", "providers.name"):
        assert "LIKE" in cols[key] and "without" in cols[key].lower(), key


def test_glossary_tables_match_split():
    assert set(load_glossary().tables) == set(TABLE_SPLIT)


def test_glossary_pii_list():
    assert set(load_glossary().pii_columns) == {"patients.ssn", "patients.drivers", "patients.passport"}


def test_glossary_columns_reference_known_tables():
    for key in load_glossary().columns:
        table, _, column = key.partition(".")
        assert table in TABLE_SPLIT and column, key


def test_links_loaded():
    links = load_glossary().links
    assert len(links) == 7
    assert "encounters.provider = providers.id" in links


def test_blocked_columns_by_role():
    g = load_glossary()
    pii = {"patients.ssn", "patients.drivers", "patients.passport"}
    assert g.blocked_columns("clinician") == pii
    assert g.blocked_columns("patient") >= pii | {"payers.revenue", "providers.encounters", "organizations.utilization"}
    assert len(g.blocked_columns("patient")) == 3 + 14 + 2 + 2


def test_payment_amount_semantics():
    # Live test C9: PAYMENT rows keep the paid money in `payments`; `amount` is empty for them.
    g = load_glossary()
    assert "payments" in g.columns["claims_transactions.amount"]
    hint = next(t for t in g.terms if t.term.startswith("insurance payment")).sql_hint
    assert "payments" in hint


def test_outstanding_balance_term():
    # Live test X2: the AI summed claims_transactions.outstanding (a per-line running balance) -> 779k instead of 211.
    from app.graph.nodes.inject_schema import _matching_terms
    g = load_glossary()
    hits = _matching_terms("What is the total outstanding patient balance on claims?", g.terms)
    assert any("outstandingp" in t.sql_hint for t in hits)
    assert "not" in g.columns["claims_transactions.outstanding"].lower()


def test_condition_type_suffix_explained():
    # First accuracy run (CL10): asked for the most common *disorder*, the AI answered
    # "Medication review due (situation)" — it didn't know the bracket at the end is the type.
    note = load_glossary().columns["conditions.description"].lower()
    assert "(disorder)" in note and "(situation)" in note and "(finding)" in note
