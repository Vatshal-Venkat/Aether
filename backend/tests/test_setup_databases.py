"""After `python -m scripts.setup_databases` has run: data is loaded and chatbot_ro is read-only."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from tests.conftest import requires_db

pytestmark = pytest.mark.db


def _scalar(url: str, sql: str):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql)).scalar()
    finally:
        engine.dispose()


def test_clinical_counts():
    requires_db("clinical")
    admin = get_settings().clinical_url(admin=True)  # admin: unaffected by row-level security
    assert _scalar(admin, "SELECT count(*) FROM patients") == 111
    assert _scalar(admin, "SELECT count(*) FROM encounters") == 5059


def test_billing_counts():
    requires_db("billing")
    ro = get_settings().billing_url()
    assert _scalar(ro, "SELECT count(*) FROM claims") == 8275
    assert _scalar(ro, "SELECT count(*) FROM providers") == 267


def test_ro_cannot_write_postgres():
    requires_db("clinical")
    engine = create_engine(get_settings().clinical_url())
    with pytest.raises(DBAPIError, match="permission denied"):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO patients (id) VALUES ('x')"))
    engine.dispose()


def test_ro_cannot_write_mysql():
    requires_db("billing")
    engine = create_engine(get_settings().billing_url())
    with pytest.raises(DBAPIError, match="denied"):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO payers (id) VALUES ('x')"))
    engine.dispose()


def test_columns_lowercase():
    requires_db("clinical")
    cols = _scalar(
        get_settings().clinical_url(admin=True),
        "SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_name = 'patients'",
    )
    assert "birthdate" in cols.split(",")
    assert "BIRTHDATE" not in cols
