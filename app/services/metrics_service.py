"""관리자 모니터링 페이지의 API 메트릭 (D10) — Grafana Cloud Prometheus 를 조회해 차트용 시계열로 돌려준다.

Grafana Cloud 는 다른 사이트에 iframe 으로 넣는 것을 막는다 (frame-ancestors 'none', 무료 티어에서 변경 불가).
그래서 대시보드를 끼워 넣는 대신 백엔드가 숫자를 가져와 프론트가 직접 그린다 — 메트릭을 외부에 공개하지 않아도 된다.

알림 룰(infra/observability/grafana-cloud/alert-rules.json)과 같은 기준: **사용자 요청만** 센다.
/metrics(Alloy 수집)·/healthz·/(헬스체크)는 뺀다.
"""
from __future__ import annotations

import time

from app.services import prometheus_client as prom

# 범위별 (기간 초, 점 간격 초, rate 창). 점은 범위마다 약 60~170개
RANGES: dict[str, tuple[int, int, str]] = {
    "1h": (3600, 60, "5m"),
    "24h": (86400, 600, "20m"),
    "7d": (604800, 3600, "2h"),
}

USER_REQ = 'job="seoganpyo-api", handler!~"/metrics|/healthz|/health|/"'

CACHE_TTL = 30  # 초 — 같은 범위를 여러 번 열어도 Grafana Cloud 쿼리는 30초에 한 번
_cache: dict[str, tuple[float, dict]] = {}


def _series(promql: str, start: int, end: int, step: int, scale: float = 1.0) -> list[dict]:
    result = prom.query_range(promql, start, end, step)
    if not result:
        return []  # 해당 기간 사용자 요청 없음
    out = []
    for ts, raw in result[0]["values"]:
        v = prom.to_float(raw)
        out.append({"t": int(float(ts)), "v": None if v is None else round(v * scale, 4)})
    return out


def _last(promql: str, end: int) -> float | None:
    result = prom.query_range(promql, end, end, 60)
    if not result or not result[0]["values"]:
        return None
    return prom.to_float(result[0]["values"][-1][1])


def get_api_metrics(range_key: str) -> dict:
    """차트 3개(초당 요청·p95·5xx) + 기간 합계. 30초 캐시."""
    now = time.time()
    hit = _cache.get(range_key)
    if hit and hit[0] > now:
        return hit[1]

    span, step, win = RANGES[range_key]
    end = int(now)
    start = end - span
    total_win = range_key  # 1h / 24h / 7d 는 PromQL 기간 표기와 같다

    payload = {
        "range": range_key,
        "step_seconds": step,
        "rps": _series(f"sum(rate(http_requests_total{{{USER_REQ}}}[{win}]))", start, end, step),
        "p95_ms": _series(
            f"histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{USER_REQ}}}[{win}])))",
            start, end, step, scale=1000),
        "errors_5xx_rps": _series(
            f'sum(rate(http_requests_total{{{USER_REQ}, status="5xx"}}[{win}]))', start, end, step),
        "total_requests": _last(f"sum(increase(http_requests_total{{{USER_REQ}}}[{total_win}]))", end),
        "total_5xx": _last(f'sum(increase(http_requests_total{{{USER_REQ}, status="5xx"}}[{total_win}]))', end),
        "api_up": None,
    }
    up = _last('max(up{job="seoganpyo-api"})', end)
    payload["api_up"] = None if up is None else up >= 1

    _cache[range_key] = (now + CACHE_TTL, payload)
    return payload
