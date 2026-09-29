"""강의 목록 API 의 SQL 쿼리 수 — N+1 회귀 방지.

CourseResponse 는 course.details · professor.details 까지 직렬화한다. 미리 불러오지 않으면
강의·교수마다 지연 로딩 쿼리가 나가 요청당 SQL 이 강의 수에 비례해 늘어난다
(2026-09-27 측정: 37강의 → 64개, docs/performance.md §3.4).
"""
import pytest
from sqlalchemy import event

from app.database import engine
from app.models.course import Course, CourseDetail
from app.models.professor import Professor, ProfessorDetail


def _seed(db, n_courses: int, n_profs: int):
    profs = []
    for i in range(n_profs):
        p = Professor(professor_id=100 + i, name=f"교수{i}", department="컴퓨터공학과")
        db.add(p)
        db.add(ProfessorDetail(professor_id=100 + i, name=f"교수{i}", research_summary="요약"))
        profs.append(p)
    db.flush()
    for i in range(n_courses):
        c = Course(course_code=f"CSE9{i:03d}", course_name=f"과목{i}", credits=3, is_english=False,
                   professor_id=profs[i % n_profs].professor_id, year=2026, semester=1,
                   course_category="전공")
        db.add(c)
        db.flush()
        db.add(CourseDetail(course_id=c.course_id, overview=f"개요{i}"))
    db.commit()


def _count_selects(client, url: str) -> tuple[int, list]:
    statements = []

    def before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        res = client.get(url)
    finally:
        event.remove(engine, "before_cursor_execute", before)
    assert res.status_code == 200
    return len(statements), res.json()


@pytest.mark.parametrize("n_courses,n_profs", [(3, 2), (20, 8)])
def test_course_list_query_count_is_constant(client, db, n_courses, n_profs):
    _seed(db, n_courses, n_profs)
    count, body = _count_selects(client, "/api/v1/courses?year=2026&semester=1")

    assert len(body) == n_courses
    # 강의(+교수 join) 1 + course_details 1 + professor_details 1 — 강의 수와 무관
    assert count <= 3, f"SELECT {count}개 — N+1 회귀 의심"


def test_course_list_still_returns_nested_details(client, db):
    _seed(db, 2, 1)
    _, body = _count_selects(client, "/api/v1/courses?year=2026&semester=1")

    first = body[0]
    assert first["details"]["overview"].startswith("개요")
    assert first["professor"]["details"]["research_summary"] == "요약"


def test_course_search_also_eager_loads(client, db):
    _seed(db, 10, 4)
    count, body = _count_selects(client, "/api/v1/courses?q=과목")

    assert len(body) == 10
    assert count <= 3, f"SELECT {count}개 — 검색 경로 N+1 회귀 의심"
