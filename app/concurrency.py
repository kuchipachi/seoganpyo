"""동시 처리 한도 (load shedding) — T1, docs/performance.md §4.2

2026-09-27 교착(docs/postmortems/2026-09-27-db-pool-deadlock.md)의 원인은
"요청을 무제한으로 받는데, 요청 하나가 스레드풀을 두 번 거치며 그 사이 DB 연결을 쥔다"였다.
동시에 처리하는 요청 수를 DB 연결 풀보다 작게 제한하면, 처리 중인 요청은 모두 연결을 받을 수 있어
교착이 생길 수 없다. 넘치는 요청은 기다리게 하지 않고 즉시 503 으로 돌려보낸다.

uvicorn `--limit-concurrency` 대신 앱에서 거는 이유:
  uvicorn 한도는 경로를 가리지 않아 **헬스체크까지 503** 을 받는다. 과부하가 90초(30초 × 3회) 넘게
  이어지면 autoheal 이 멀쩡히 버티는 서버를 재시작했다 (로컬 재현: 4분 과부하 중 2회 재시작).
  여기서는 헬스체크·메트릭을 한도에서 빼고, 한도를 풀 크기보다 1 작게 잡아 헬스체크용 연결을 남긴다.

환경변수
  MAX_CONCURRENT_REQUESTS  0(기본) = 끔. 운영은 DB_POOL_SIZE + DB_MAX_OVERFLOW - 1 (현재 14)
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# 한도에서 제외 — 헬스체크(autoheal 판정)와 메트릭 수집은 과부하 중에도 응답해야 한다
EXEMPT_PATHS = frozenset({"/healthz", "/", "/metrics"})

_BUSY_BODY = json.dumps({
    "detail": {
        "code": "SERVER_BUSY",
        "title": "요청이 많습니다",
        "message": "지금 접속자가 많아 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    }
}, ensure_ascii=False).encode("utf-8")


class ConcurrencyLimitMiddleware:
    """순수 ASGI 미들웨어 — 처리 중인 HTTP 요청 수가 limit 에 도달하면 즉시 503.

    이벤트 루프 하나에서만 증감하고 검사와 증가 사이에 await 가 없으므로 락이 필요 없다.
    카운트는 응답 전송이 끝날 때까지 유지된다 (응답 변환 단계까지 포함 — 그 동안에도 DB 연결을 쥐므로).
    """

    def __init__(self, app, limit: int, exempt_paths: frozenset[str] = EXEMPT_PATHS):
        self.app = app
        self.limit = limit
        self.exempt_paths = exempt_paths
        self.active = 0
        self.shed = 0  # 거절 누계 (로그용)

    def _route_path(self, scope) -> str:
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root):   # uvicorn --root-path /backend 대응
            path = path[len(root):] or "/"
        return path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.limit <= 0 or self._route_path(scope) in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        if self.active >= self.limit:
            self.shed += 1
            if self.shed == 1 or self.shed % 100 == 0:
                logger.warning("동시 처리 한도(%d) 초과 — 503 거절 누계 %d", self.limit, self.shed)
            await send({
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"retry-after", b"1"),
                    (b"content-length", str(len(_BUSY_BODY)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": _BUSY_BODY})
            return

        self.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active -= 1
