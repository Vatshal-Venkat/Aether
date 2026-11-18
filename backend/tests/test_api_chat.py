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
def client(tmp_path):
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
    # Plan 5: the service layer's audit log etc. go to a temporary folder, never the real data/ files.
    from app.api.ops_routes import get_ops
    from app.ops import Ops
    ops = Ops.for_tests(tmp_path)
    app.dependency_overrides[get_ops] = lambda: ops
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


# --- GET /api/sessions/{id}: the conversation history -------------------------------------------------
def test_session_history_is_scoped_to_role_and_patient(client, tmp_path):
    # Final review: the endpoint returned every turn of a session (clinician answers, other patients' turns).
    from app.memory.store import ConversationStore, Turn
    deps = client.app.dependency_overrides[get_deps]()
    deps.memory = ConversationStore(tmp_path / "m.sqlite")
    for role, pid, q in [("clinician", None, "How many?"), ("patient", "p2", "My meds?")]:
        deps.memory.add(Turn(session_id="abc", role=role, patient_id=pid, question=q, standalone=q, answer="x", kind="answer"))
    clin = client.get("/api/sessions/abc", params={"role": "clinician"}).json()
    assert [t["question"] for t in clin] == ["How many?"]
    p2 = client.get("/api/sessions/abc", params={"role": "patient", "patient_id": "p2"}).json()
    assert [t["question"] for t in p2] == ["My meds?"]
    assert client.get("/api/sessions/abc", params={"role": "patient", "patient_id": "p1"}).json() == []
    assert client.get("/api/sessions/abc").status_code == 422  # role is required
    assert "patient_id" not in clin[0]


# --- /metrics and /api/audit ------------------------------------------------------------------------
def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200 and "aether_requests_total" in resp.text


def test_audit_api_disabled_by_default(client):
    assert client.get("/api/audit").status_code == 404


def test_audit_api_when_enabled(client):
    from app.api.ops_routes import get_ops
    ops = client.app.dependency_overrides[get_ops]()
    ops.audit_api_enabled = True
    client.post("/api/chat", json={"message": "How many patients?", "role": "clinician"})
    rows = client.get("/api/audit", params={"limit": 5}).json()
    assert rows and rows[0]["question"] == "How many patients?" and rows[0]["kind"] == "answer"


# --- Plan 5: rate limit and result pages ------------------------------------------------------------
def test_rate_limit_429(client):
    from app.api.ops_routes import get_ops
    from app.ops.ratelimit import SlidingWindow
    client.app.dependency_overrides[get_ops]().limiter = SlidingWindow(limit=2, window=60)
    for _ in range(2):
        assert client.post("/api/chat", json={"message": "Hi", "role": "clinician"}).status_code == 200
    resp = client.post("/api/chat", json={"message": "Hi", "role": "clinician"})
    assert resp.status_code == 429 and "Too many questions" in resp.json()["detail"]
    assert float(resp.headers["Retry-After"]) > 0
    assert client.post("/api/chat/stream", json={"message": "Hi", "role": "clinician"}).status_code == 429


def test_result_pages_scoped(client):
    from app.api.chat import get_runner
    from app.graph.state import QueryResult
    big = ChatResult(answer="250 rows.", kind="answer",
                     table=QueryResult(columns=["n"], rows=[[i] for i in range(250)], total_rows=250, truncated=False))
    client.app.dependency_overrides[get_runner] = lambda: (lambda *a: big)
    body = client.post("/api/chat", json={"message": "List", "role": "clinician"}).json()
    rid = body["table"]["result_id"]
    assert len(body["table"]["rows"]) == 100
    page = client.get(f"/api/results/{rid}", params={"page": 3, "role": "clinician"}).json()
    assert page["rows"][0] == [200] and len(page["rows"]) == 50 and page["pages"] == 3
    assert client.get(f"/api/results/{rid}", params={"page": 2, "role": "patient", "patient_id": "p1"}).status_code == 404
    assert client.get(f"/api/results/{rid}", params={"page": 9, "role": "clinician"}).status_code == 422
