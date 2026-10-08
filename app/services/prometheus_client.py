"""Prometheus HTTP API 클라이언트 — 관리자 메트릭(/admin/metrics)과 관리자 챗 query_prometheus 가 같이 쓴다.

운영은 Grafana Cloud Prometheus (D13), 로컬은 make up-obs 의 prometheus:9090.

환경변수
  PROMETHEUS_URL            운영: https://prometheus-prod-XX-....grafana.net/api/prom  (뒤에 /api/v1/... 를 붙임)
                            빈 값이면 메트릭 조회를 끈다
  GRAFANA_CLOUD_PROM_USER   Grafana Cloud Prometheus 인스턴스 ID — Alloy 와 같은 값
  GRAFANA_CLOUD_READ_TOKEN  읽기 전용 토큰 (metrics:read). Alloy 의 GRAFANA_CLOUD_TOKEN(쓰기 전용)과 분리
                            둘 다 있으면 Basic 인증, 없으면 인증 없이 (로컬 Prometheus)
"""
from __future__ import annotations

import math
import os

import httpx

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").strip().rstrip("/")


class PrometheusError(Exception):
    pass


def auth() -> tuple[str, str] | None:
    user = os.getenv("GRAFANA_CLOUD_PROM_USER", "").strip()
    token = os.getenv("GRAFANA_CLOUD_READ_TOKEN", "").strip()
    return (user, token) if user and token else None


def query_range(promql: str, start: int, end: int, step: int) -> list[dict]:
    """range query 결과의 series 목록 ([{"metric": {...}, "values": [[ts, "값"], ...]}])"""
    if not PROMETHEUS_URL:
        raise PrometheusError("PROMETHEUS_URL 이 설정되지 않았습니다")
    try:
        with httpx.Client(timeout=10.0, auth=auth()) as client:
            res = client.get(f"{PROMETHEUS_URL}/api/v1/query_range",
                             params={"query": promql, "start": start, "end": end, "step": step})
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPError as e:
        raise PrometheusError(f"Prometheus 쿼리 실패: {e}") from e
    if data.get("status") != "success":
        raise PrometheusError(data.get("error", "unknown"))
    return data["data"]["result"]


def to_float(raw: str) -> float | None:
    """Prometheus 값 문자열 → float. NaN·Inf 는 None (데이터 없음)"""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v
