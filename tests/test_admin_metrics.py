"""관리자 모니터링 메트릭 (/admin/metrics) — Grafana Cloud Prometheus 를 흉내 내 검증."""
import pytest

from app.api import admin as admin_api
from app.services import metrics_service
from app.services import prometheus_client as prom
from app.services.user_service import create_access_token, hash_password


@pytest.fixture
def admin_headers(db):
    from app.models.user import User
    u = User(student_id=20200001, name="관리자", email="admin@sogang.ac.kr",
             password=hash_password("password123"), is_approved=True, role="admin")
    db.add(u)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(u.student_id)}"}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    metrics_service._cache.clear()
    monkeypatch.setattr(admin_api, "PROMETHEUS_URL", "https://prom.example/api/prom")
    monkeypatch.setattr(prom, "PROMETHEUS_URL", "https://prom.example/api/prom")


def fake_prom(calls):
    """PromQL 에 따라 가짜 series 를 돌려준다. 호출한 쿼리는 calls 에 쌓인다."""
    def query_range(promql, start, end, step):
        calls.append(promql)
        if promql.startswith("max(up"):
            return [{"metric": {}, "values": [[end, "1"]]}]
        if "increase(" in promql:
            return [{"metric": {}, "values": [[end, "5" if "5xx" in promql else "120"]]}]
        if "histogram_quantile" in promql:
            return [{"metric": {}, "values": [[start, "0.131"], [start + step, "NaN"]]}]
        if "5xx" in promql:
            return []  # 5xx 없음
        return [{"metric": {}, "values": [[start, "0.5"], [start + step, "0.25"]]}]
    return query_range


def test_metrics_shape_and_user_requests_only(client, admin_headers, monkeypatch):
    calls = []
    monkeypatch.setattr(prom, "query_range", fake_prom(calls))

    res = client.get("/admin/metrics?range=1h", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["range"] == "1h" and body["step_seconds"] == 60
    assert [p["v"] for p in body["rps"]] == [0.5, 0.25]
    assert [p["v"] for p in body["p95_ms"]] == [131.0, None]   # 초 → ms, NaN → None
    assert body["errors_5xx_rps"] == []
    assert body["total_requests"] == 120 and body["total_5xx"] == 5
    assert body["api_up"] is True
    # 알림 룰과 같은 기준 — /metrics·헬스체크 제외 (up 은 수집 상태라 예외)
    assert all('handler!~"/metrics|/healthz|/health|/"' in q for q in calls if not q.startswith("max(up"))


def test_metrics_cached_30s(client, admin_headers, monkeypatch):
    calls = []
    monkeypatch.setattr(prom, "query_range", fake_prom(calls))
    client.get("/admin/metrics?range=24h", headers=admin_headers)
    n = len(calls)
    client.get("/admin/metrics?range=24h", headers=admin_headers)
    assert len(calls) == n  # 두 번째는 캐시


def test_metrics_requires_admin(client, auth_headers):
    assert client.get("/admin/metrics", headers=auth_headers).status_code == 403
    assert client.get("/admin/metrics").status_code in (401, 403)


def test_metrics_invalid_range(client, admin_headers):
    assert client.get("/admin/metrics?range=30d", headers=admin_headers).status_code == 422


def test_metrics_disabled_without_prometheus(client, admin_headers, monkeypatch):
    monkeypatch.setattr(admin_api, "PROMETHEUS_URL", "")
    assert client.get("/admin/metrics", headers=admin_headers).status_code == 503


def test_metrics_upstream_failure_is_502(client, admin_headers, monkeypatch):
    def boom(*a, **k):
        raise prom.PrometheusError("timeout")
    monkeypatch.setattr(prom, "query_range", boom)
    assert client.get("/admin/metrics", headers=admin_headers).status_code == 502


def test_auth_only_when_both_set(monkeypatch):
    monkeypatch.delenv("GRAFANA_CLOUD_READ_TOKEN", raising=False)
    monkeypatch.setenv("GRAFANA_CLOUD_PROM_USER", "123")
    assert prom.auth() is None  # 로컬 Prometheus — 인증 없음
    monkeypatch.setenv("GRAFANA_CLOUD_READ_TOKEN", "glc_x")
    assert prom.auth() == ("123", "glc_x")
