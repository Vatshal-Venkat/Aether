"""/health: a quick "is everything plugged in?" check."""

from fastapi.testclient import TestClient

from app.api import health
from app.main import create_app


def _client(monkeypatch, clinical="ok", billing="ok") -> TestClient:
    monkeypatch.setattr(health, "check_db", lambda db: clinical if db == "clinical" else billing)
    return TestClient(create_app(with_pipeline=False))


def test_health_ok(monkeypatch):
    body = _client(monkeypatch).get("/health").json()
    assert body["status"] == "ok"
    assert body["clinical"] == "ok" and body["billing"] == "ok"
    assert body["llm_provider"] in ("groq", "gemini", "ollama")


def test_health_degraded(monkeypatch):
    resp = _client(monkeypatch, billing="error: refused").get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["billing"] == "error: refused"


def test_cors_allows_localhost_vite(monkeypatch):
    resp = _client(monkeypatch).options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
