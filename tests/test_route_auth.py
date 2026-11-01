"""재발 방지 — 특정 학생을 가리키는 경로는 반드시 인증을 거친다.

경로에 {student_id} 가 들어간 엔드포인트가 인증 의존성 없이 열리면,
학번만 바꿔 다른 학생의 데이터를 조회·수정할 수 있다 (OWASP API1: BOLA).
2026-11 레거시 장바구니·수강이력 경로 6개가 이 상태로 운영에 열려 있었다.

새 라우터가 이 규칙을 어기면 이 테스트가 실패한다.
"""
from fastapi.routing import APIRoute

from app.api.admin import get_current_admin
from app.dependencies import get_current_student_id
from app.main import app

AUTH_DEPS = {get_current_student_id, get_current_admin}


def _uses_auth(dependant) -> bool:
    """의존성 트리 어딘가에 인증 함수가 있는지"""
    for dep in dependant.dependencies:
        if dep.call in AUTH_DEPS or _uses_auth(dep):
            return True
    return False


def test_student_scoped_routes_require_auth():
    offenders = [
        f"{sorted(r.methods)} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute) and "{student_id}" in r.path and not _uses_auth(r.dependant)
    ]
    assert not offenders, f"인증 없이 학번으로 접근하는 경로: {offenders}"


def test_rule_actually_checks_something():
    """규칙이 공회전하지 않는지 — {student_id} 경로가 실제로 존재하고 모두 인증을 거친다"""
    scoped = [r for r in app.routes if isinstance(r, APIRoute) and "{student_id}" in r.path]
    assert scoped, "{student_id} 경로가 하나도 없음 — 규칙이 아무것도 검사하지 않는다"
    assert all(_uses_auth(r.dependant) for r in scoped)
