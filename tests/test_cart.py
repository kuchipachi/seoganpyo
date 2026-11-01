"""
장바구니(Cart) API 테스트 — /api/v1/cart (토큰의 학번으로만 접근)

- 장바구니 조회, 강의 추가, 삭제
- 중복 추가 방지
- 없는 강의 추가 방지
- 인증 없음 401, 다른 학생의 장바구니에 손댈 수 없음
"""
import pytest


class TestCartGet:
    def test_get_empty_cart(self, client, test_user, auth_headers):
        res = client.get("/api/v1/cart", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_get_cart_with_item(self, client, test_user, test_cart, auth_headers):
        res = client.get("/api/v1/cart", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["course_id"] == test_cart.course_id


class TestCartAdd:
    def test_add_to_cart(self, client, test_user, test_course, auth_headers):
        res = client.post("/api/v1/cart", json={"course_id": test_course.course_id}, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["course_id"] == test_course.course_id
        assert data["student_id"] == test_user.student_id

    def test_add_duplicate_course(self, client, test_user, test_cart, auth_headers):
        """이미 담긴 강의를 다시 추가하면 409"""
        res = client.post("/api/v1/cart", json={"course_id": test_cart.course_id}, headers=auth_headers)
        assert res.status_code == 409

    def test_add_nonexistent_course(self, client, test_user, auth_headers):
        """존재하지 않는 강의 추가 시 404"""
        res = client.post("/api/v1/cart", json={"course_id": 99999}, headers=auth_headers)
        assert res.status_code == 404

    def test_add_two_different_courses(self, client, test_user, test_course, test_course2, auth_headers):
        client.post("/api/v1/cart", json={"course_id": test_course.course_id}, headers=auth_headers)
        client.post("/api/v1/cart", json={"course_id": test_course2.course_id}, headers=auth_headers)
        res = client.get("/api/v1/cart", headers=auth_headers)
        assert len(res.json()) == 2


class TestCartRemove:
    def test_remove_from_cart(self, client, test_user, test_cart, auth_headers):
        res = client.delete(f"/api/v1/cart/{test_cart.id}", headers=auth_headers)
        assert res.status_code == 204

        # 삭제 후 비어있어야 함
        res2 = client.get("/api/v1/cart", headers=auth_headers)
        assert res2.json() == []

    def test_remove_nonexistent_cart_item(self, client, test_user, auth_headers):
        res = client.delete("/api/v1/cart/99999", headers=auth_headers)
        assert res.status_code == 404


class TestCartAuth:
    """인증·본인 확인 — 학생 A 의 장바구니는 A 만"""

    def test_unauthorized(self, client):
        assert client.get("/api/v1/cart").status_code == 401
        assert client.post("/api/v1/cart", json={"course_id": 1}).status_code == 401
        assert client.delete("/api/v1/cart/1").status_code == 401

    def test_other_student_cannot_see_cart(self, client, test_cart, test_user2, auth_headers2):
        """B 로 조회하면 A 의 항목이 보이지 않는다"""
        res = client.get("/api/v1/cart", headers=auth_headers2)
        assert res.status_code == 200
        assert res.json() == []

    def test_other_student_cannot_delete_cart_item(self, client, test_user, test_cart, test_user2, auth_headers, auth_headers2):
        """B 가 A 의 장바구니 항목 id 로 삭제하면 404, A 의 항목은 그대로"""
        res = client.delete(f"/api/v1/cart/{test_cart.id}", headers=auth_headers2)
        assert res.status_code == 404
        assert len(client.get("/api/v1/cart", headers=auth_headers).json()) == 1

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/v1/users/{sid}/cart"),
        ("post", "/api/v1/users/{sid}/cart"),
        ("delete", "/api/v1/users/{sid}/cart/1"),
        ("get", "/api/v1/users/{sid}/history"),
        ("post", "/api/v1/users/{sid}/history"),
        ("delete", "/api/v1/users/{sid}/history/1"),
    ])
    def test_legacy_student_id_routes_removed(self, client, test_user, method, path):
        """학번을 경로로 받던 옛 경로는 없어야 한다 (본인 확인 없이 누구의 데이터든 접근 가능했음)"""
        res = getattr(client, method)(path.format(sid=test_user.student_id))
        assert res.status_code in (404, 405)
