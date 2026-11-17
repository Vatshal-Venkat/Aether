"""HTTP endpoints: /api/chat, /api/patients, /api/schema."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api.chat import get_runner
from app.api.deps import get_deps
from app.graph.runner import ChatResult
from app.main import create_app
from tests.fakes import ScriptedLLM, make_deps


@pytest.fixture
def client():
    # One shared connection: the endpoint reads from a worker thread, and an in-memory
    # SQLite database only exists on the connection that created it.
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id TEXT, first TEXT, last TEXT, birthdate TEXT, gender TEXT, ssn TEXT)"))
        conn.execute(text("INSERT INTO patients VALUES ('p1', 'Zed12', 'Zulu3', '1980-01-01', 'M', '999-11-2222')"))
        conn.execute(text("INSERT INTO patients VALUES ('p2', 'Abe604', 'Bode78', '1990-05-05', 'F', '999-33-4444')"))
    deps = make_deps(ScriptedLLM(), engines={"clinical": engine})
    calls = []

    def fake_runner(deps, question, role, patient_id, session_id):
        calls.append((question, role, patient_id))
        return ChatResult(answer="There are 111 patients.", kind="answer")

    app = create_app(with_pipeline=False)
    app.dependency_overrides[get_deps] = lambda: deps
    app.dependency_overrides[get_runner] = lambda: fake_runner
    c = TestClient(app)
    c.calls = calls
    return c


def test_chat_returns_result(client):
    resp = client.post("/api/chat", json={"message": "How many patients?", "role": "clinician"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "There are 111 patients."
    assert client.calls == [("How many patients?", "clinician", None)]


def test_patient_role_requires_patient_id(client):
    assert client.post("/api/chat", json={"message": "my meds?", "role": "patient"}).status_code == 422


def test_unknown_patient_id_rejected(client):
    resp = client.post("/api/chat", json={"message": "my meds?", "role": "patient", "patient_id": "nope"})
    assert resp.status_code == 422


def test_known_patient_id_accepted(client):
    resp = client.post("/api/chat", json={"message": "my meds?", "role": "patient", "patient_id": "p2"})
    assert resp.status_code == 200 and client.calls[-1] == ("my meds?", "patient", "p2")


def test_message_length_validated(client):
    assert client.post("/api/chat", json={"message": "", "role": "clinician"}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 1001, "role": "clinician"}).status_code == 422


def test_patients_list_has_no_pii(client):
    body = client.get("/api/patients").json()
    assert [p["name"] for p in body] == ["Abe604 Bode78", "Zed12 Zulu3"]
    assert set(body[0]) == {"id", "name", "birthdate", "gender"}


def test_schema_endpoint_no_pii(client):
    body = client.get("/api/schema", params={"db": "clinical"}).json()
    patients = next(t for t in body if t["table"] == "patients")
    assert "ssn" not in [c["name"] for c in patients["columns"]]
    assert patients["description"]


def _db_down(*args, **kwargs):
    from sqlalchemy.exc import OperationalError

    raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_patients_503_when_db_down(client, monkeypatch):
    # Review I3: a database outage is a friendly 503, not a 500 stack trace.
    monkeypatch.setattr("app.api.catalog_routes.list_patients", _db_down)
    resp = client.get("/api/patients")
    assert resp.status_code == 503 and "database" in resp.json()["detail"].lower()


def test_chat_patient_check_503_when_db_down(client, monkeypatch):
    monkeypatch.setattr("app.api.chat.patient_exists", _db_down)
    resp = client.post("/api/chat", json={"message": "my meds?", "role": "patient", "patient_id": "p2"})
    assert resp.status_code == 503 and "database" in resp.json()["detail"].lower()


def test_chat_503_when_pipeline_unavailable():
    app = create_app(with_pipeline=False)
    resp = TestClient(app).post("/api/chat", json={"message": "hi", "role": "clinician"})
    assert resp.status_code == 503


# --- POST /api/chat/stream: Server-Sent Events -----------------------------------------------------
from app.api.chat import get_stream_runner  # noqa: E402


@pytest.fixture
def stream_client(client):
    def fake_stream(deps, question, role, patient_id, session_id):
        yield {"event": "progress", "data": {"step": "route"}}
        yield {"event": "progress", "data": {"step": "execute", "db": "clinical"}}
        yield {"event": "final", "data": ChatResult(answer="Done.", kind="answer").model_dump()}

    client.app.dependency_overrides[get_stream_runner] = lambda: fake_stream
    return client


def test_stream_endpoint_sends_sse(stream_client):
    resp = stream_client.post("/api/chat/stream", json={"message": "How many?", "role": "clinician"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert body.index("event: progress") < body.index("event: final")
    assert 'data: {"step": "execute", "db": "clinical"}' in body
    assert '"answer": "Done."' in body


def test_stream_endpoint_rejects_unknown_patient(stream_client):
    resp = stream_client.post("/api/chat/stream", json={"message": "x", "role": "patient", "patient_id": "nope"})
    assert resp.status_code == 422
