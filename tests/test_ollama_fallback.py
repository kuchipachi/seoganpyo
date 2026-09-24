"""Ollama 호출 실패 처리 단위 테스트.

AWS 에는 Ollama 가 없으므로 연결 실패·시간 초과가 5분 대기가 아니라
의미 있는 503 으로 끝나는지 확인한다. 실제 Ollama 없이 httpx 전송 계층을 대체해 검증.
"""
import importlib

import httpx
import pytest
from fastapi import HTTPException

from app.services import crawl_service, syllabus_service


def _mock_client(monkeypatch, module, handler):
    """module 안의 httpx.Client 를 MockTransport 를 쓰는 클라이언트로 교체."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "Client", factory)


def _raise(exc_cls):
    def handler(request):
        raise exc_cls("simulated", request=request)
    return handler


# ─── syllabus_service.summarize_with_ollama ───────────────────
@pytest.mark.parametrize("exc_cls", [httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout])
def test_summarize_unreachable_returns_503(monkeypatch, exc_cls):
    _mock_client(monkeypatch, syllabus_service, _raise(exc_cls))

    with pytest.raises(HTTPException) as exc_info:
        syllabus_service.summarize_with_ollama("강의계획서 본문")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "SUMMARY_UNAVAILABLE"
    assert exc_info.value.detail["title"] == "요약 준비 중입니다"


def test_summarize_ollama_error_response_returns_502(monkeypatch):
    _mock_client(monkeypatch, syllabus_service, lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(HTTPException) as exc_info:
        syllabus_service.summarize_with_ollama("강의계획서 본문")

    assert exc_info.value.status_code == 502


def test_summarize_success_parses_json(monkeypatch):
    sent = {}

    def handler(request):
        sent["url"] = str(request.url)
        return httpx.Response(200, json={"response": '{"course_code": "CSE1001"}'})

    _mock_client(monkeypatch, syllabus_service, handler)

    result = syllabus_service.summarize_with_ollama("강의계획서 본문")

    assert result == {"course_code": "CSE1001"}
    assert sent["url"] == syllabus_service.OLLAMA_URL


# ─── crawl_service._summarize_research_area ───────────────────
def test_research_summary_unreachable_returns_none(monkeypatch):
    _mock_client(monkeypatch, crawl_service, _raise(httpx.ConnectError))

    assert crawl_service._summarize_research_area("인공지능 및 기계학습 연구") is None


# ─── 환경변수 ────────────────────────────────────────────────
def test_ollama_settings_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.test:11434/api/generate")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_TIMEOUT", "20")
    try:
        for module in (syllabus_service, crawl_service):
            importlib.reload(module)
            assert module.OLLAMA_URL == "http://ollama.test:11434/api/generate"
            assert module.OLLAMA_MODEL == "test-model"
            assert module.OLLAMA_TIMEOUT == 20
    finally:
        monkeypatch.undo()
        importlib.reload(syllabus_service)
        importlib.reload(crawl_service)
