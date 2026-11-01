"""
강의(Courses) API 테스트

- 전체 조회, 검색(이름/코드), 필터(영어강의), 페이지네이션
- 단일 강의 상세 조회
"""
import pytest


class TestCourseList:
    def test_get_all_courses(self, client, test_course, test_course2):
        res = client.get("/api/v1/courses?year=2026&semester=1")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2

    def test_search_by_name(self, client, test_course, test_course2):
        res = client.get("/api/v1/courses?year=2026&semester=1&q=인공지능")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["course_name"] == "인공지능"

    def test_search_by_code(self, client, test_course, test_course2):
        res = client.get("/api/v1/courses?year=2026&semester=1&q=CSE3201")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["course_code"] == "CSE3201"

    def test_filter_english_only(self, client, test_course, test_course2):
        res = client.get("/api/v1/courses?year=2026&semester=1&is_english=true")
        assert res.status_code == 200
        data = res.json()
        assert all(c["is_english"] for c in data)
        assert len(data) == 1

    def test_pagination_limit(self, client, test_course, test_course2):
        res = client.get("/api/v1/courses?year=2026&semester=1&limit=1")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1

    def test_pagination_offset(self, client, test_course, test_course2):
        res_all = client.get("/api/v1/courses?year=2026&semester=1")
        res_offset = client.get("/api/v1/courses?year=2026&semester=1&offset=1")
        assert len(res_offset.json()) == len(res_all.json()) - 1

    def test_empty_result_for_unknown_year(self, client, test_course):
        res = client.get("/api/v1/courses?year=1999&semester=1")
        assert res.status_code == 200
        assert res.json() == []


class TestCourseDetail:
    def test_get_course_detail(self, client, test_course):
        res = client.get(f"/api/v1/courses/{test_course.course_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["course_id"] == test_course.course_id
        assert data["course_name"] == "인공지능"

    def test_get_nonexistent_course(self, client):
        res = client.get("/api/v1/courses/99999")
        assert res.status_code == 404


class TestCourseListParamBounds:
    """음수·과대 페이지 파라미터가 DB 까지 가 500 이 되지 않는다 (Schemathesis 발견, 2026-11)"""

    def test_negative_limit_is_422(self, client):
        assert client.get("/api/v1/courses?limit=-5").status_code == 422

    def test_negative_offset_is_422(self, client):
        assert client.get("/api/v1/courses?offset=-1").status_code == 422

    def test_oversized_limit_is_422(self, client):
        assert client.get("/api/v1/courses?limit=100000").status_code == 422

    def test_zero_and_normal_limit_ok(self, client):
        assert client.get("/api/v1/courses?limit=0").status_code == 200
        assert client.get("/api/v1/courses?limit=10&offset=0").status_code == 200
