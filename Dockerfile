# backend 런타임.
# docker CLI 는 포함하지 않음 — prod 는 docker.sock 을 마운트하지 않아 admin_assistant.get_container_status 가
# 동작할 수 없고(챗 도구 목록에서도 자동 제외), 로컬 dev 는 Dockerfile.dev + 호스트 docker.sock 을 사용.
# 베이스 이미지는 Debian 코드네임 핀 필수 — `python:3.11-slim` 단독 태그는 Docker Hub 가
# 임의 시점에 다음 stable 로 떠내려보냄 (예: 2026-05 경 bookworm(12) → trixie(13)).
# 같은 Dockerfile 이 시점에 따라 다른 결과를 내는 재현성 사고를 막기 위해 코드네임 고정.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Seoul

WORKDIR /app

# 종속성 설치.
# pip / wheel / setuptools 를 먼저 업그레이드 — python:3.11-slim-bookworm 의 기본 버전이
#   pip 24.0  (CVE-2025-8869, CVE-2026-1703, CVE-2026-3219, CVE-2026-6357 — 4건)
#   wheel 0.45.1 (CVE-2026-24049 — path traversal → privilege escalation)
#   setuptools 79.0.1 (path traversal via wheel vendoring)
# 모두 패키지 설치 단계에서 영향을 주므로 requirements 설치 전에 갱신.
# 버전 핀 박음 (hadolint DL3013) — 재현성 + 미래의 새 CVE 자동 회귀 방지.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==26.1.1 wheel==0.47.0 setuptools==82.0.1 \
    && pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt

# Non-root 사용자 생성 — Trivy DS-002 (root 권한 회피).
# prod backend 는 docker.sock 미마운트라 root 권한 필요 없음 (docker-compose.yml 주석 참조).
# UID/GID 10001 — 호스트 일반 사용자(보통 1000번대) 와 겹치지 않게 고른 값.
ARG APP_UID=10001
RUN groupadd --system --gid ${APP_UID} appuser \
    && useradd --system --uid ${APP_UID} --gid ${APP_UID} --no-create-home --shell /usr/sbin/nologin appuser

# 애플리케이션 코드 및 데이터 복사 — appuser 소유로.
# data 는 docker-compose 의 ./data:/app/data 볼륨 마운트로 런타임에 host 측이 덮어쓰지만,
# 빌드 시점에 chown 해두면 init 시 그 안에서 만들어지는 파일도 appuser 소유.
COPY --chown=appuser:appuser ./app ./app
COPY --chown=appuser:appuser ./static ./static
COPY --chown=appuser:appuser ./data ./data

USER appuser

# HEALTHCHECK — Trivy DS-026. docker-compose 의 healthcheck 가 빌드된 이미지엔 안 들어가서
# Dockerfile 에 별도 선언. docker run 단독 시도 헬스 추적되고 Trivy 룰도 만족.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/', timeout=5).status < 500 else 1)" || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
