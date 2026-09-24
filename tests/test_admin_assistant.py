"""admin_assistant 도구 6개(DB) 단위 테스트.

인프라 도구(query_loki_logs, query_prometheus, get_container_status)는
외부 시스템 의존이라 단위 테스트에선 제외.
"""
import json
from datetime import datetime, timedelta

import pytest

from app.models.activity import History
from app.models.portfolio import PortfolioEvaluation
from app.services import admin_assistant


@pytest.fixture
def history_2026_1(db, test_user, test_user2, test_course, test_course2):
    rows = [
        History(student_id=test_user.student_id, course_code=test_course.course_code, year=2026, semester=1),
        History(student_id=test_user.student_id, course_code=test_course2.course_code, year=2026, semester=1),
        History(student_id=test_user2.student_id, course_code=test_course.course_code, year=2026, semester=1),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


# ─── search_courses ────────────────────────────────────────────
def test_search_courses_partial_match(db, test_course):
    result = admin_assistant.search_courses(db, "인공", limit=5)
    assert len(result) == 1
    assert result[0]["course_name"] == "인공지능"
    assert result[0]["professor_name"] == "김교수"


def test_search_courses_filter_by_year_semester(db, test_course, test_course2):
    result = admin_assistant.search_courses(db, "지능", year=2026, semester=1)
    assert len(result) == 1
    result_other = admin_assistant.search_courses(db, "지능", year=2025)
    assert result_other == []


def test_search_courses_no_match(db, test_course):
    assert admin_assistant.search_courses(db, "존재하지않는과목") == []


# ─── get_popular_courses ───────────────────────────────────────
def test_popular_courses_ranks_by_history_count(db, history_2026_1, test_course, test_course2):
    result = admin_assistant.get_popular_courses(db, 2026, 1, limit=10)
    assert len(result) == 2
    assert result[0]["course_code"] == test_course.course_code  # 2건
    assert result[0]["history_count"] == 2
    assert result[0]["rank"] == 1
    assert result[1]["course_code"] == test_course2.course_code  # 1건
    assert result[1]["history_count"] == 1


def test_popular_courses_empty_when_no_history(db, test_course):
    assert admin_assistant.get_popular_courses(db, 2026, 1) == []


# ─── get_user_stats ────────────────────────────────────────────
def test_user_stats_counts_users(db, test_user, test_user2):
    stats = admin_assistant.get_user_stats(db)
    assert stats["total_users"] == 2
    assert stats["approved_users"] == 2
    assert stats["pending_approval"] == 0
    assert stats["admins"] == 0


# ─── get_history_coverage ──────────────────────────────────────
def test_history_coverage_reports_distinct_students(db, history_2026_1):
    cov = admin_assistant.get_history_coverage(db, 2026, 1)
    assert cov["distinct_students"] == 2
    assert cov["total_history_rows"] == 3
    assert cov["distinct_course_codes_used"] == 2
    assert cov["total_course_codes_in_db"] == 2
    assert cov["course_match_ratio"] == 1.0
    assert cov["avg_courses_per_student"] == 1.5


def test_history_coverage_empty(db):
    cov = admin_assistant.get_history_coverage(db, 2099, 1)
    assert cov["distinct_students"] == 0
    assert cov["total_history_rows"] == 0
    assert cov["course_match_ratio"] == 0


# ─── get_unused_courses ────────────────────────────────────────
def test_unused_courses_excludes_used_codes(db, history_2026_1, test_course, test_course2):
    # 모든 코스가 history에 있으니 unused 빈 결과
    result = admin_assistant.get_unused_courses(db, 2026, 1)
    assert result == []


def test_unused_courses_includes_never_matched(db, test_course, test_course2):
    # history 없음 → 두 강의 모두 unused
    result = admin_assistant.get_unused_courses(db, 2026, 1)
    codes = {r["course_code"] for r in result}
    assert codes == {test_course.course_code, test_course2.course_code}


# ─── get_evaluation_stats ──────────────────────────────────────
@pytest.fixture
def sample_evaluations(db, test_user):
    """별점 스케일(alignment_score 0~6) 기준 샘플.
    6 → ★3 버킷, 3 → ★1~2 버킷."""
    now = datetime.utcnow()
    rows = [
        PortfolioEvaluation(
            student_id=test_user.student_id,
            status="completed",
            alignment_score=6,  # ★3
            created_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1) + timedelta(seconds=15),
        ),
        PortfolioEvaluation(
            student_id=test_user.student_id,
            status="completed",
            alignment_score=3,  # ★1~2
            created_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2) + timedelta(seconds=20),
        ),
        PortfolioEvaluation(
            student_id=test_user.student_id,
            status="failed",
            error_message=json.dumps({"code": "rate_limited", "title": "한도 도달"}),
            created_at=now - timedelta(hours=3),
        ),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


def test_evaluation_stats_groups_by_status_and_code(db, sample_evaluations):
    stats = admin_assistant.get_evaluation_stats(db, days=1)
    assert stats["total"] == 3
    assert stats["by_status"] == {"completed": 2, "failed": 1}
    assert stats["failure_codes"] == {"rate_limited": 1}
    assert stats["score_distribution"]["★3"] == 1
    assert stats["score_distribution"]["★1~2"] == 1
    assert stats["avg_duration_seconds"] is not None
    assert stats["avg_duration_seconds"] > 0
    assert len(stats["sample_failures"]) == 1
    assert stats["sample_failures"][0]["code"] == "rate_limited"


def test_evaluation_stats_excludes_old_rows(db, test_user):
    old = PortfolioEvaluation(
        student_id=test_user.student_id,
        status="completed",
        alignment_score=4,  # 별점 스케일
        created_at=datetime.utcnow() - timedelta(days=30),
        completed_at=datetime.utcnow() - timedelta(days=30),
    )
    db.add(old)
    db.commit()
    stats = admin_assistant.get_evaluation_stats(db, days=7)
    assert stats["total"] == 0


# ─── 메타데이터 ────────────────────────────────────────────────
DB_TOOL_NAMES = {
    "search_courses",
    "get_popular_courses",
    "get_user_stats",
    "get_history_coverage",
    "get_unused_courses",
    "get_evaluation_stats",
}
INFRA_TOOL_NAMES = {"query_prometheus", "get_container_status"}


def test_all_tools_complete():
    names = {t["name"] for t in admin_assistant.ALL_TOOLS}
    assert names == DB_TOOL_NAMES | INFRA_TOOL_NAMES


def test_tool_registry_always_has_db_tools():
    names = {t["name"] for t in admin_assistant.TOOL_REGISTRY}
    assert DB_TOOL_NAMES <= names
    assert names <= DB_TOOL_NAMES | INFRA_TOOL_NAMES


# ─── 인프라 도구 조건부 노출 ───────────────────────────────────
def _reload_assistant(monkeypatch, prometheus_url, socket_exists):
    import importlib
    import os

    if prometheus_url is None:
        monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    else:
        monkeypatch.setenv("PROMETHEUS_URL", prometheus_url)
    real_exists = os.path.exists
    monkeypatch.setattr(
        os.path, "exists",
        lambda p: socket_exists if p == "/var/run/docker.sock" else real_exists(p),
    )
    return importlib.reload(admin_assistant)


@pytest.fixture
def restore_assistant():
    yield
    import importlib
    importlib.reload(admin_assistant)


def test_infra_tools_hidden_when_unavailable(monkeypatch, restore_assistant):
    mod = _reload_assistant(monkeypatch, prometheus_url="", socket_exists=False)
    names = {t["name"] for t in mod.TOOL_REGISTRY}
    assert names == DB_TOOL_NAMES
    assert "query_prometheus" not in mod.TOOLS_BY_NAME


def test_infra_tools_shown_when_available(monkeypatch, restore_assistant):
    mod = _reload_assistant(monkeypatch, prometheus_url="http://prometheus:9090", socket_exists=True)
    names = {t["name"] for t in mod.TOOL_REGISTRY}
    assert names == DB_TOOL_NAMES | INFRA_TOOL_NAMES


def test_prometheus_default_when_env_absent(monkeypatch, restore_assistant):
    # 호스트 실행(MCP 서버 등) — 환경변수 자체가 없으면 localhost 기본값으로 도구 유지
    mod = _reload_assistant(monkeypatch, prometheus_url=None, socket_exists=False)
    assert mod.PROMETHEUS_URL == "http://localhost:9090"
    assert "query_prometheus" in mod.TOOLS_BY_NAME


def test_query_prometheus_without_url_returns_error(monkeypatch):
    monkeypatch.setattr(admin_assistant, "PROMETHEUS_URL", "")
    result = admin_assistant.query_prometheus("up")
    assert "error" in result


def test_container_status_docker_failure_is_error_not_empty(monkeypatch):
    # docker.sock 미마운트 → docker ps 가 비정상 종료. 빈 목록([])이 아니라 에러로 알려야 함
    import subprocess

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="Cannot connect to the Docker daemon")

    monkeypatch.setattr(admin_assistant.subprocess, "run", fake_run)
    result = admin_assistant.get_container_status()
    assert len(result) == 1 and "error" in result[0]
    assert "Docker daemon" in result[0]["error"]


def test_db_tools_set_matches_registry():
    db_tool_names = {t["name"] for t in admin_assistant.TOOL_REGISTRY if t["fn"].__module__ == "app.services.admin_assistant"}
    # DB_TOOLS는 명시적 화이트리스트 — 도구 추가 시 함께 갱신해야 함
    assert admin_assistant.DB_TOOLS.issubset(db_tool_names)
    for name in admin_assistant.DB_TOOLS:
        assert name in admin_assistant.TOOLS_BY_NAME
