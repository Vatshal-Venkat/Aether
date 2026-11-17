"""PostgreSQL row-level security: in patient mode the database itself hides other patients' rows."""

import pytest
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.db.rls import set_query_context
from tests.conftest import requires_db


def test_patient_role_requires_id():
    with pytest.raises(ValueError):
        set_query_context(conn=None, role="patient", patient_id=None)


@pytest.fixture(scope="module")
def ro_engine():
    requires_db("clinical")
    engine = create_engine(get_settings().clinical_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def some_patient_id():
    requires_db("clinical")
    admin = create_engine(get_settings().clinical_url(admin=True))
    with admin.connect() as conn:
        pid = conn.execute(text("SELECT id FROM patients ORDER BY id LIMIT 1")).scalar()
    admin.dispose()
    return pid


def _count(engine, sql, role=None, pid=None):
    with engine.begin() as conn:
        if role:
            set_query_context(conn, role, pid)
        return conn.execute(text(sql)).scalar()


@pytest.mark.db
def test_clinician_sees_all(ro_engine):
    assert _count(ro_engine, "SELECT count(*) FROM patients", "clinician") == 111


@pytest.mark.db
def test_patient_sees_only_self(ro_engine, some_patient_id):
    with ro_engine.begin() as conn:
        set_query_context(conn, "patient", some_patient_id)
        ids = conn.execute(text("SELECT id FROM patients")).scalars().all()
    assert ids == [some_patient_id]


@pytest.mark.db
def test_patient_sees_only_own_encounters(ro_engine, some_patient_id):
    with ro_engine.begin() as conn:
        set_query_context(conn, "patient", some_patient_id)
        owners = set(conn.execute(text("SELECT DISTINCT patient FROM encounters")).scalars())
    assert owners == {some_patient_id}


@pytest.mark.db
def test_no_context_sees_nothing(ro_engine):
    assert _count(ro_engine, "SELECT count(*) FROM patients") == 0


@pytest.mark.db
def test_or_1_equals_1_cannot_escape(ro_engine, some_patient_id):
    sql = "SELECT count(*) FROM patients WHERE 1=1 OR id IS NOT NULL"
    assert _count(ro_engine, sql, "patient", some_patient_id) == 1


@pytest.mark.db
def test_context_does_not_leak_across_transactions(ro_engine, some_patient_id):
    assert _count(ro_engine, "SELECT count(*) FROM patients", "clinician") == 111
    assert _count(ro_engine, "SELECT count(*) FROM patients") == 0
