"""권한 매트릭스 — 인증·관리자 권한·본인 확인을 전 경로에 걸쳐 고정한다 (API 보안 점검 2026-11).

1. 공개로 정한 경로(PUBLIC) 외에는 토큰 없이 401/403
2. 학생 토큰으로 /admin/* 는 403
3. 학생 B 는 학생 A 의 게시글·댓글·수강이력·포트폴리오·평가·쪽지를 바꾸거나 볼 수 없다 (OWASP API1: BOLA)

새 경로를 공개로 열려면 PUBLIC 에 이유와 함께 추가해야 한다 — 실수로 열리는 것을 막는다.
"""
import re

import pytest
from fastapi.routing import APIRoute

from app.main import app

# 인증 없이 여는 것으로 정한 경로 — (메서드, 경로): 이유
PUBLIC = {
    ("GET", "/"): "앱 상태",
    ("GET", "/healthz"): "컨테이너 헬스체크",
    ("GET", "/metrics"): "Prometheus 수집 — Caddy 가 외부 접근 차단",
    ("POST", "/auth/send-email"): "가입 전 이메일 인증",
    ("POST", "/auth/verify-code"): "가입 전 이메일 인증",
    ("POST", "/auth/register"): "회원가입",
    ("GET", "/auth/approve"): "관리자 승인 링크 — 추측 불가 토큰(uuid4)으로 확인",
    ("POST", "/auth/login"): "로그인",
    ("POST", "/auth/reset-password/send-email"): "비밀번호 재설정",
    ("POST", "/auth/reset-password"): "비밀번호 재설정 (인증번호로 확인)",
    ("POST", "/admin/login"): "관리자 로그인",
    ("GET", "/api/v1/courses"): "강의 목록 (공개 정보)",
    ("GET", "/api/v1/courses/code/{course_code}"): "강의 조회 (공개 정보)",
    ("GET", "/api/v1/courses/{course_id}"): "강의 조회 (공개 정보)",
    ("GET", "/api/v1/syllabus/{course_id}"): "강의계획서 요약 (공개 정보)",
    ("GET", "/api/v1/syllabus/{course_id}/pdf"): "강의계획서 PDF (공개 정보)",
    ("GET", "/api/v1/syllabus/{course_id}/pdf/{filename:path}"): "위와 같음 — 파일명은 무시하고 DB 해시로 찾음",
    ("GET", "/api/v1/professors"): "교수 목록 (공개 정보)",
    ("GET", "/api/v1/professors/{professor_id}"): "교수 조회 (공개 정보)",
    ("GET", "/api/v1/community/{category}"): "게시판 읽기",
    ("GET", "/api/v1/community/{category}/{post_id}"): "게시글 읽기",
}


def _routes():
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield m, r.path


def _url(path: str) -> str:
    """경로 파라미터를 더미 값으로 채운다 — 인증은 파라미터 검증보다 먼저 걸려야 한다"""
    path = path.replace("{filename:path}", "x.pdf")
    return re.sub(r"{(\w+)}", lambda m: "general" if m.group(1) == "category" else "1", path)


def _call(client, method, path, headers=None):
    kw = {"headers": headers or {}}
    if method in ("POST", "PUT", "PATCH"):
        kw["json"] = {}
    return client.request(method, _url(path), **kw)


def test_public_list_matches_reality():
    """PUBLIC 에 적었는데 실제로는 없는 경로가 없는지 (목록이 낡지 않게)"""
    existing = set(_routes())
    stale = [k for k in PUBLIC if k not in existing]
    assert not stale, f"없어진 경로가 PUBLIC 에 남아 있음: {stale}"


@pytest.mark.parametrize("method,path", [k for k in _routes() if k not in PUBLIC])
def test_requires_auth(client, method, path):
    res = _call(client, method, path)
    assert res.status_code in (401, 403), f"{method} {path} → {res.status_code} (토큰 없이 통과)"


@pytest.mark.parametrize("method,path", [k for k in _routes() if k[1].startswith("/admin") and k not in PUBLIC])
def test_student_cannot_use_admin(client, auth_headers, method, path):
    res = _call(client, method, path, headers=auth_headers)
    assert res.status_code == 403, f"{method} {path} → {res.status_code} (학생 토큰으로 관리자 API)"


# ── 3. 본인 확인 — 데이터 주인 A(test_user), 공격자 B(test_user2) ────────────

@pytest.fixture
def owned(db, test_user, test_post):
    """A 의 데이터 한 벌"""
    from app.models.activity import History
    from app.models.admin_message import AdminMessage
    from app.models.portfolio import PortfolioEntry, PortfolioEvaluation
    from app.models.post import Comment

    rows = {
        "comment": Comment(post_id=test_post.id, content="A 의 댓글", student_id=test_user.student_id),
        "history": History(student_id=test_user.student_id, course_code="CSE1001"),
        "entry": PortfolioEntry(student_id=test_user.student_id, kind="project", order_index=0),
        "evaluation": PortfolioEvaluation(student_id=test_user.student_id, status="done"),
        "message": AdminMessage(recipient_id=test_user.student_id, content="A 에게 보낸 쪽지"),
    }
    db.add_all(rows.values())
    db.commit()
    for r in rows.values():
        db.refresh(r)
    rows["post"] = test_post
    return rows


def _still_there(db, row):
    db.expire_all()
    return db.get(type(row), row.id) is not None


def test_other_cannot_edit_or_delete_post(client, db, owned, test_user2, auth_headers2):
    p = owned["post"]
    assert client.patch(f"/api/v1/community/{p.category}/{p.id}", json={"title": "B 가 바꿈", "content": "x"},
                        headers=auth_headers2).status_code == 403
    assert client.delete(f"/api/v1/community/{p.category}/{p.id}", headers=auth_headers2).status_code == 403
    db.expire_all()
    assert db.get(type(p), p.id).title == "테스트 게시글"


def test_other_cannot_delete_comment(client, db, owned, test_user2, auth_headers2):
    p, c = owned["post"], owned["comment"]
    res = client.delete(f"/api/v1/community/{p.category}/{p.id}/comments/{c.id}", headers=auth_headers2)
    assert res.status_code == 403
    assert _still_there(db, c)


def test_other_cannot_touch_history(client, db, owned, test_user2, auth_headers2):
    h = owned["history"]
    assert client.patch(f"/history/{h.id}", json={"is_retake": True}, headers=auth_headers2).status_code >= 400
    assert client.delete(f"/history/{h.id}", headers=auth_headers2).status_code >= 400
    db.expire_all()
    row = db.get(type(h), h.id)
    assert row is not None and not row.is_retake


def test_other_cannot_touch_portfolio_entry(client, db, owned, test_user2, auth_headers2):
    e = owned["entry"]
    assert client.patch(f"/api/v1/portfolio/{e.id}", json={}, headers=auth_headers2).status_code >= 400
    assert client.delete(f"/api/v1/portfolio/{e.id}", headers=auth_headers2).status_code == 404
    assert _still_there(db, e)


def test_other_cannot_read_evaluation(client, owned, test_user2, auth_headers2):
    ev = owned["evaluation"]
    assert client.get(f"/api/v1/portfolio/evaluate/{ev.id}", headers=auth_headers2).status_code == 404


def test_other_cannot_mark_message_read(client, db, owned, test_user2, auth_headers2):
    m = owned["message"]
    assert client.patch(f"/api/v1/users/me/messages/{m.id}/read", headers=auth_headers2).status_code == 404
    db.expire_all()
    assert db.get(type(m), m.id).is_read is False


def test_owner_lists_do_not_leak_to_other(client, owned, test_user2, auth_headers2):
    """B 의 '내 것' 목록에 A 의 데이터가 섞이지 않는다"""
    assert client.get("/history/me", headers=auth_headers2).json() == []
    assert all(not v for v in client.get("/api/v1/portfolio", headers=auth_headers2).json().values())
    assert client.get("/api/v1/users/me/messages/unread", headers=auth_headers2).json() == []
