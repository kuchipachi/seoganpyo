"""강의계획서 요약 업로드 엔드포인트 인증 테스트."""
from app.services import syllabus_service

PDF = {"file": ("syllabus.pdf", b"%PDF-1.4 dummy", "application/pdf")}


def test_summarize_unauthorized(client):
    res = client.post("/api/v1/syllabus/summarize", files=PDF)
    assert res.status_code == 401


def test_summarize_invalid_token(client):
    res = client.post(
        "/api/v1/syllabus/summarize",
        files=PDF,
        headers={"Authorization": "Bearer invalid"},
    )
    assert res.status_code == 401


def test_summarize_authorized_reaches_service(client, auth_headers, monkeypatch):
    called = {}

    def fake_process(db, file_bytes):
        called["bytes"] = file_bytes
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="강의 코드 또는 학기 정보를 찾을 수 없습니다")

    monkeypatch.setattr(syllabus_service, "process_syllabus", fake_process)

    res = client.post("/api/v1/syllabus/summarize", files=PDF, headers=auth_headers)

    assert called["bytes"] == b"%PDF-1.4 dummy"
    assert res.status_code == 422
