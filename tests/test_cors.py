"""CORS — 임의 출처를 반영하지 않는다 (OWASP CORS Misconfiguration, 보안 점검 2026-11)."""
import importlib

import pytest
from fastapi.testclient import TestClient


def _client(monkeypatch, origins):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", origins)
    import app.main
    importlib.reload(app.main)
    return TestClient(app.main.app)


def test_unknown_origin_not_reflected(monkeypatch):
    c = _client(monkeypatch, "https://seoganpyo.example")
    r = c.get("/api/v1/courses", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"


def test_allowed_origin_permitted(monkeypatch):
    c = _client(monkeypatch, "https://seoganpyo.example")
    r = c.get("/api/v1/courses", headers={"Origin": "https://seoganpyo.example"})
    assert r.headers.get("access-control-allow-origin") == "https://seoganpyo.example"


@pytest.fixture(autouse=True)
def _restore():
    yield
    import app.main
    importlib.reload(app.main)
