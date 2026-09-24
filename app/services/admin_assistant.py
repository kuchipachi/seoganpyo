"""운영 어시스턴트가 호출하는 read-only 도구 모음.

이 모듈의 함수들은 두 곳에서 재사용된다:
  1. scripts/mcp_seoganpyo.py — Claude Desktop용 MCP 서버
  2. app/api/admin_chat.py — admin 페이지 챗 UI 백엔드 (Gemini tool use)

규칙:
  - DB 도구는 첫 인자로 SQLAlchemy Session을 받는다.
  - 인프라 도구(Loki/Prometheus/Docker)는 Session 불필요.
  - 반환값은 JSON-직렬화 가능한 dict/list만.
  - 변경 작업은 절대 하지 않는다 (read-only).
  - 시연 환경 가정: PII 마스킹 없음 (B안).
"""
import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.activity import History
from app.models.course import Course
from app.models.portfolio import PortfolioEvaluation
from app.models.user import User

# ─── 인프라 엔드포인트 ─────────────────────────────────────────────
# PROMETHEUS_URL 을 빈 값으로 두면(운영 EC2 — 관측 스택 없음) query_prometheus 도구를 챗에 노출하지 않는다.
# 환경변수 자체가 없으면 호스트 실행(MCP 서버 등)을 위해 localhost 기본값 유지.
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").strip()
DOCKER_SOCKET = "/var/run/docker.sock"


# ─── 1. 강의 검색 (시나리오 2: 사용 통계) ──────────────────────────
def search_courses(
    db: Session,
    query: str,
    year: Optional[int] = None,
    semester: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """강의명으로 강의를 검색합니다 (부분 일치)."""
    q = db.query(Course).filter(Course.course_name.ilike(f"%{query}%"))
    if year is not None:
        q = q.filter(Course.year == year)
    if semester is not None:
        q = q.filter(Course.semester == semester)
    rows = (
        q.order_by(Course.year.desc(), Course.semester.desc(), Course.course_name)
        .limit(limit)
        .all()
    )
    return [
        {
            "course_id": c.course_id,
            "course_code": c.course_code,
            "course_name": c.course_name,
            "year": c.year,
            "semester": c.semester,
            "credits": c.credits,
            "professor_name": c.professor.name if c.professor else None,
        }
        for c in rows
    ]


# ─── 2. 인기 과목 TOP N (시나리오 2: 사용 통계) ───────────────────
def get_popular_courses(
    db: Session,
    year: int,
    semester: int,
    limit: int = 10,
) -> list[dict]:
    """수강이력(histories) 기준 가장 많이 들은 과목 TOP N.

    histories는 OCR 시간표 업로드 결과로 채워지는 테이블.
    """
    rows = (
        db.query(
            History.course_code,
            func.count(History.id).label("count"),
        )
        .filter(History.year == year, History.semester == semester)
        .group_by(History.course_code)
        .order_by(func.count(History.id).desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []

    course_codes = [r.course_code for r in rows]
    course_map = {
        c.course_code: c
        for c in db.query(Course)
        .filter(
            Course.year == year,
            Course.semester == semester,
            Course.course_code.in_(course_codes),
        )
        .all()
    }
    return [
        {
            "rank": idx + 1,
            "course_code": r.course_code,
            "course_name": course_map[r.course_code].course_name
            if r.course_code in course_map
            else "(DB에 없음)",
            "professor_name": course_map[r.course_code].professor.name
            if r.course_code in course_map and course_map[r.course_code].professor
            else None,
            "history_count": r.count,
        }
        for idx, r in enumerate(rows)
    ]


# ─── 3. 사용자 통계 (시나리오 2: 사용 통계) ───────────────────────
def get_user_stats(db: Session) -> dict:
    """전체 사용자 통계."""
    total = db.query(func.count(User.student_id)).scalar() or 0
    approved = (
        db.query(func.count(User.student_id))
        .filter(User.is_approved.is_(True))
        .scalar()
        or 0
    )
    admins = (
        db.query(func.count(User.student_id))
        .filter(User.role == "admin")
        .scalar()
        or 0
    )
    post_blocked = (
        db.query(func.count(User.student_id))
        .filter(User.can_post.is_(False))
        .scalar()
        or 0
    )
    comment_blocked = (
        db.query(func.count(User.student_id))
        .filter(User.can_comment.is_(False))
        .scalar()
        or 0
    )

    sem_rows = (
        db.query(User.current_semester, func.count(User.student_id))
        .filter(User.is_approved.is_(True))
        .group_by(User.current_semester)
        .order_by(User.current_semester)
        .all()
    )
    return {
        "total_users": total,
        "approved_users": approved,
        "pending_approval": total - approved,
        "admins": admins,
        "post_blocked": post_blocked,
        "comment_blocked": comment_blocked,
        "by_current_semester": [
            {"semester": s if s is not None else "미설정", "count": c}
            for s, c in sem_rows
        ],
    }


# ─── 4. 학기별 수강이력 커버리지 (시나리오 4: OCR 품질) ───────────
def get_history_coverage(db: Session, year: int, semester: int) -> dict:
    """OCR 매칭 결과(history) 커버리지 — 얼마나 많은 학생/과목이 잡혔나."""
    distinct_students = (
        db.query(func.count(func.distinct(History.student_id)))
        .filter(History.year == year, History.semester == semester)
        .scalar()
        or 0
    )
    total_rows = (
        db.query(func.count(History.id))
        .filter(History.year == year, History.semester == semester)
        .scalar()
        or 0
    )
    used_codes = (
        db.query(func.count(func.distinct(History.course_code)))
        .filter(History.year == year, History.semester == semester)
        .scalar()
        or 0
    )
    total_codes = (
        db.query(func.count(func.distinct(Course.course_code)))
        .filter(Course.year == year, Course.semester == semester)
        .scalar()
        or 0
    )
    return {
        "year": year,
        "semester": semester,
        "distinct_students": distinct_students,
        "total_history_rows": total_rows,
        "avg_courses_per_student": round(total_rows / distinct_students, 2)
        if distinct_students
        else 0,
        "distinct_course_codes_used": used_codes,
        "total_course_codes_in_db": total_codes,
        "course_match_ratio": round(used_codes / total_codes, 3)
        if total_codes
        else 0,
    }


# ─── 5. 사용된 적 없는 과목 (시나리오 4: OCR 품질) ────────────────
def get_unused_courses(
    db: Session,
    year: int,
    semester: int,
    limit: int = 30,
) -> list[dict]:
    """DB엔 있지만 history에 한 번도 매칭되지 않은 과목 — OCR 매칭 실패 후보."""
    used_codes = {
        r[0]
        for r in db.query(func.distinct(History.course_code))
        .filter(History.year == year, History.semester == semester)
        .all()
    }
    rows = (
        db.query(Course)
        .filter(Course.year == year, Course.semester == semester)
        .order_by(Course.course_name)
        .all()
    )
    unused = [c for c in rows if c.course_code not in used_codes][:limit]
    return [
        {
            "course_code": c.course_code,
            "course_name": c.course_name,
            "name_length": len(c.course_name),
            "professor_name": c.professor.name if c.professor else None,
            "credits": c.credits,
        }
        for c in unused
    ]


# ─── 6. AI 평가 통계 (시나리오 6: 사용자 영향) ────────────────────
def get_evaluation_stats(db: Session, days: int = 7) -> dict:
    """포트폴리오 AI 평가 통계 — 성공/실패 분포 + 실패 사유."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PortfolioEvaluation)
        .filter(PortfolioEvaluation.created_at >= cutoff)
        .all()
    )
    total = len(rows)
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    failure_codes: dict[str, int] = {}
    sample_failures: list[dict] = []
    for r in rows:
        if r.status != "failed" or not r.error_message:
            continue
        try:
            payload = json.loads(r.error_message)
            code = payload.get("code", "unknown")
            title = payload.get("title", "")
        except (json.JSONDecodeError, TypeError):
            code = "unparseable"
            title = (r.error_message or "")[:80]
        failure_codes[code] = failure_codes.get(code, 0) + 1
        if len(sample_failures) < 5:
            sample_failures.append(
                {
                    "evaluation_id": r.id,
                    "student_id": r.student_id,
                    "code": code,
                    "title": title,
                    "created_at": r.created_at.isoformat(),
                }
            )

    durations = [
        (r.completed_at - r.created_at).total_seconds()
        for r in rows
        if r.status == "completed" and r.completed_at and r.created_at
    ]
    avg_duration = round(sum(durations) / len(durations), 2) if durations else None

    # 0~6 정수 → 0~3 별점(0.5 단위) UI 와 동일 구간으로 버킷.
    score_buckets = {"★0~1": 0, "★1~2": 0, "★2~3": 0, "★3": 0}
    for r in rows:
        if r.status != "completed" or r.alignment_score is None:
            continue
        s = r.alignment_score
        if s <= 1:
            score_buckets["★0~1"] += 1
        elif s <= 3:
            score_buckets["★1~2"] += 1
        elif s <= 5:
            score_buckets["★2~3"] += 1
        else:
            score_buckets["★3"] += 1

    return {
        "period_days": days,
        "total": total,
        "by_status": by_status,
        "failure_codes": failure_codes,
        "avg_duration_seconds": avg_duration,
        "score_distribution": score_buckets,
        "sample_failures": sample_failures,
    }


# ─── 7. Prometheus 메트릭 쿼리 (시나리오 3: 운영 알람) ────────────
def query_prometheus(
    promql: str,
    minutes: int = 60,
    step_seconds: int = 60,
) -> dict:
    """PromQL로 Prometheus를 쿼리합니다 (range query).

    예시 PromQL:
      sum(rate(http_requests_total{status="5xx"}[5m]))
      histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

    Args:
        promql: PromQL 표현식
        minutes: 최근 몇 분 (기본 60)
        step_seconds: 샘플링 간격 (기본 60초)
    """
    # POSIX epoch — datetime.utcnow().timestamp()는 컨테이너 TZ=Asia/Seoul과
    # 충돌해 9시간 미래로 해석되는 함정이 있어 time.time() 사용.
    if not PROMETHEUS_URL:
        return {"error": "PROMETHEUS_URL 이 설정되지 않아 메트릭을 조회할 수 없습니다.", "promql": promql}

    end = int(time.time())
    start = end - minutes * 60

    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": step_seconds,
                },
            )
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPError as e:
        return {"error": f"Prometheus 쿼리 실패: {e}", "promql": promql}

    if data.get("status") != "success":
        return {"error": data.get("error", "unknown"), "promql": promql}

    series = data["data"]["result"]
    summary = []
    for s in series[:10]:  # 너무 많으면 잘라냄
        labels = s["metric"]
        values = s["values"]
        if not values:
            continue
        nums = [float(v[1]) for v in values if v[1] not in ("NaN", "+Inf", "-Inf")]
        summary.append(
            {
                "labels": labels,
                "samples": len(values),
                "min": round(min(nums), 4) if nums else None,
                "max": round(max(nums), 4) if nums else None,
                "avg": round(sum(nums) / len(nums), 4) if nums else None,
                "last": round(nums[-1], 4) if nums else None,
            }
        )
    return {
        "promql": promql,
        "minutes": minutes,
        "step_seconds": step_seconds,
        "series_count": len(series),
        "summary": summary,
    }


# ─── 8. Docker 컨테이너 상태 (시나리오 3: 운영 알람) ──────────────
def get_container_status() -> list[dict]:
    """seoganpyo-* 도커 컨테이너 상태와 리소스 사용률을 반환합니다."""
    try:
        ps_result = subprocess.run(
            [
                "docker", "ps", "-a",
                "--filter", "name=seoganpyo",
                "--format", "{{.Names}}\t{{.Status}}\t{{.State}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return [{"error": f"docker ps 실행 실패: {e}"}]
    # docker.sock 미마운트 등으로 실패하면 stdout 이 비어 "컨테이너 없음"으로 오인되므로 에러로 반환
    if ps_result.returncode != 0:
        return [{"error": f"docker ps 실행 실패: {ps_result.stderr.strip() or f'exit {ps_result.returncode}'}"}]

    rows: list[dict] = []
    name_state: dict[str, dict] = {}
    for line in ps_result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, status, state = parts[0], parts[1], parts[2]
        name_state[name] = {"name": name, "status": status, "state": state}

    if not name_state:
        return []

    # 실행 중인 컨테이너만 stats 수집
    running = [n for n, info in name_state.items() if info["state"] == "running"]
    if running:
        try:
            stats_result = subprocess.run(
                [
                    "docker", "stats", "--no-stream",
                    "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}",
                    *running,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in stats_result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) < 4:
                    continue
                name, cpu, mem, mem_pct = parts
                if name in name_state:
                    name_state[name].update(
                        {"cpu_percent": cpu, "memory": mem, "memory_percent": mem_pct}
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    rows = list(name_state.values())
    rows.sort(key=lambda x: (x.get("state") != "running", x["name"]))
    return rows


# ─── 도구 메타데이터 (Gemini tool use용 — 어댑터에서 사용) ─────────
ALL_TOOLS = [
    {
        "name": "search_courses",
        "description": "강의명으로 강의를 검색합니다 (부분 일치). 학기 필터 가능.",
        "fn": search_courses,
        "params": {
            "query": {"type": "string", "required": True, "description": "검색할 강의명"},
            "year": {"type": "integer", "required": False, "description": "연도"},
            "semester": {"type": "integer", "required": False, "description": "학기 (1 또는 2)"},
            "limit": {"type": "integer", "required": False, "description": "최대 개수 (기본 20)"},
        },
    },
    {
        "name": "get_popular_courses",
        "description": "수강이력 기준 가장 많이 들은 과목 TOP N. OCR 매칭 빈도와 동일한 의미.",
        "fn": get_popular_courses,
        "params": {
            "year": {"type": "integer", "required": True, "description": "연도"},
            "semester": {"type": "integer", "required": True, "description": "학기"},
            "limit": {"type": "integer", "required": False, "description": "TOP N (기본 10)"},
        },
    },
    {
        "name": "get_user_stats",
        "description": "전체 사용자 통계 — 가입자 수, 관리자 수, 학기별 분포 등.",
        "fn": get_user_stats,
        "params": {},
    },
    {
        "name": "get_history_coverage",
        "description": "특정 학기의 수강이력 커버리지 — OCR 업로드/매칭 사용 정도 지표.",
        "fn": get_history_coverage,
        "params": {
            "year": {"type": "integer", "required": True, "description": "연도"},
            "semester": {"type": "integer", "required": True, "description": "학기"},
        },
    },
    {
        "name": "get_unused_courses",
        "description": "DB엔 있지만 수강이력에 한 번도 잡히지 않은 과목 — OCR 매칭 실패 후보 발굴용.",
        "fn": get_unused_courses,
        "params": {
            "year": {"type": "integer", "required": True, "description": "연도"},
            "semester": {"type": "integer", "required": True, "description": "학기"},
            "limit": {"type": "integer", "required": False, "description": "최대 개수 (기본 30)"},
        },
    },
    {
        "name": "get_evaluation_stats",
        "description": "포트폴리오 AI 평가 통계 — 최근 N일 성공/실패 분포 및 실패 사유 코드별.",
        "fn": get_evaluation_stats,
        "params": {
            "days": {"type": "integer", "required": False, "description": "최근 며칠 (기본 7)"},
        },
    },
    {
        "name": "query_prometheus",
        "description": (
            "PromQL로 Prometheus 메트릭을 시간 범위 쿼리합니다. "
            "응답엔 시리즈별 min/max/avg/last 값 요약 포함. "
            "예: 'sum(rate(http_requests_total{status=\"5xx\"}[5m]))'"
        ),
        "fn": query_prometheus,
        "params": {
            "promql": {"type": "string", "required": True, "description": "PromQL 표현식"},
            "minutes": {"type": "integer", "required": False, "description": "최근 몇 분 (기본 60)"},
            "step_seconds": {"type": "integer", "required": False, "description": "샘플링 간격(초, 기본 60)"},
        },
    },
    {
        "name": "get_container_status",
        "description": "seoganpyo-* 도커 컨테이너의 상태와 CPU/메모리 사용률을 조회합니다.",
        "fn": get_container_status,
        "params": {},
    },
]




def _tool_available(name: str) -> bool:
    """인프라 도구는 실제로 쓸 수 있는 환경에서만 노출 — 못 쓰는 도구를 LLM 이 호출해 헛답하는 것 방지."""
    if name == "query_prometheus":
        return bool(PROMETHEUS_URL)
    if name == "get_container_status":
        return os.path.exists(DOCKER_SOCKET)
    return True


# 현재 환경에서 챗에 노출할 도구
TOOL_REGISTRY = [t for t in ALL_TOOLS if _tool_available(t["name"])]

# 함수명 → 함수 매핑 (어댑터에서 빠른 lookup용)
TOOLS_BY_NAME = {t["name"]: t for t in TOOL_REGISTRY}

# DB 세션이 필요한 도구 이름 — 어댑터가 세션 인자 주입 여부를 판단할 때 사용
DB_TOOLS = {
    "search_courses",
    "get_popular_courses",
    "get_user_stats",
    "get_history_coverage",
    "get_unused_courses",
    "get_evaluation_stats",
}
