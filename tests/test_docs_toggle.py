"""API 문서 노출 토글 — 운영(ENABLE_API_DOCS=0)에서는 /docs·/openapi.json 이 닫힌다.

docs/security-assessment.md #6 — 문서·명세가 공격자에게 엔드포인트 지도를 준다.
"""
import importlib

from fastapi.testclient import TestClient


def _client(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    else:
        monkeypatch.setenv("ENABLE_API_DOCS", value)
    import app.main
    importlib.reload(app.main)
    return TestClient(app.main.app)


def test_docs_disabled_in_prod(monkeypatch):
    c = _client(monkeypatch, "0")
    assert c.get("/docs").status_code == 404
    assert c.get("/redoc").status_code == 404
    assert c.get("/openapi.json").status_code == 404
    # 실제 API 는 그대로 동작
    assert c.get("/healthz").status_code == 200


def test_docs_enabled_by_default(monkeypatch):
    c = _client(monkeypatch, None)
    assert c.get("/openapi.json").status_code == 200


def _restore():
    import app.main
    importlib.reload(app.main)


def teardown_module(module):
    _restore()
