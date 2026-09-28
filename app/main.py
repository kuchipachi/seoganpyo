import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from app.api import auth, upload, courses, cart, history, users, admin, admin_chat, admin_security, admin_security_chat, syllabus, posts, contact, professors, portfolio, timetables
from app.database import engine, Base, SessionLocal
from app.concurrency import ConcurrencyLimitMiddleware
from app.models import user, course, professor, activity, post, report, notice, portfolio as portfolio_models, contact as contact_model, admin_message  # noqa: F401 — Base 테이블 등록용
from app.services import portfolio_migration
from app.services.special_courses_service import seed_special_courses

# Root logger 설정 — Promtail/Loki에서 INFO 이상 로그 수집 가능하도록
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx 는 매 요청을 INFO 로 찍는데 Discord webhook URL 같은 시크릿이 노출됨
# (Loki 수집되면 누구나 채널 스팸 가능). WARNING 이상만 보이게 격상.
logging.getLogger("httpx").setLevel(logging.WARNING)

# 서버 실행 시 DB 테이블 생성
Base.metadata.create_all(bind=engine)

# 특수 과목(수시·군이러닝) 시드 — idempotent, 부팅마다 신규 행만 추가.
_seed_db = SessionLocal()
try:
    _seeded = seed_special_courses(_seed_db)
    if _seeded:
        logging.getLogger(__name__).info("special courses seeded: %d rows", _seeded)
finally:
    _seed_db.close()

# 포트폴리오 평가 테이블 마이그레이션 — 새 컬럼(rubric, section_scores) 자동 추가 +
# 옛 0~100 스케일 alignment_score 를 0~6 별점 스케일로 환산.
_pf_db = SessionLocal()
try:
    portfolio_migration.run(engine, _pf_db)
finally:
    _pf_db.close()

app = FastAPI(title="서간표 통합 서버")

Instrumentator().instrument(app).expose(app)

os.makedirs("static/uploads/posts", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# OWASP ZAP 베이스라인 스캔이 잡는 보안 헤더 결함을 일괄 차단.
# 헤더 의미:
#   Strict-Transport-Security    : HTTPS 강제 (HSTS). HTTP 환경에선 브라우저가 무시 — 무해.
#   X-Frame-Options=DENY         : 다른 사이트가 iframe 으로 우리 페이지를 감싸지 못함 (clickjacking 차단).
#   X-Content-Type-Options       : 브라우저의 MIME sniffing 차단 (선언된 Content-Type 만 신뢰).
#   Referrer-Policy              : 외부로 referrer 누출 최소화 (cross-origin 시 origin 만).
#   Permissions-Policy           : 카메라/마이크/위치 등 강한 권한 기본 차단 — 우리 백엔드는 안 씀.
#   Content-Security-Policy      : 응답 본문이 대부분 JSON 이지만 /docs Swagger UI HTML 도 있으므로
#                                  cdn.jsdelivr.net (Swagger 자산) + 'unsafe-inline' 까지 허용.
#                                  frame-ancestors 'none' 으로 X-Frame-Options 와 이중 차단.
#   Cross-Origin-Resource-Policy : 다른 origin 에서 우리 응답을 fetch/embed 못 하게 (Spectre 류 차단).
#                                  same-origin = 우리 도메인만 허용. ZAP "CORP Missing" 결함 차단.
#   Cache-Control                : API 응답(JSON) 은 항상 fresh — 토큰/세션 정보 등 캐시 X.
#                                  static 자산(/static/*) 과 메트릭(/metrics) 은 캐싱 정상 — 예외.
#                                  ZAP "Storable and Cacheable Content" 결함 차단.
# setdefault 사용 — 라우터가 명시적으로 다른 값을 셋팅하면 그쪽 우선.
_NO_STORE_SKIP_PREFIXES = ("/static/", "/metrics")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        # static 자산 + Prometheus /metrics 는 캐싱 허용 (성능). 그 외 API 응답은 no-store.
        path = request.url.path
        if not any(path.startswith(p) for p in _NO_STORE_SKIP_PREFIXES):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


# 동시 처리 한도 (T1) — 가장 안쪽에 둬서 503 응답에도 보안 헤더·CORS 헤더가 붙게 한다.
# MAX_CONCURRENT_REQUESTS 미설정(0)이면 꺼짐. 근거는 app/concurrency.py
app.add_middleware(ConcurrencyLimitMiddleware, limit=int(os.getenv("MAX_CONCURRENT_REQUESTS", "0")))

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(courses.router)
app.include_router(cart.router)
app.include_router(timetables.router)
app.include_router(history.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(admin_chat.router)
app.include_router(admin_security.router)
app.include_router(admin_security_chat.router)
app.include_router(syllabus.router)
app.include_router(posts.router)
app.include_router(contact.router)
app.include_router(professors.router)
app.include_router(portfolio.router)

@app.get("/healthz", include_in_schema=False)
def healthz():
    """컨테이너 헬스체크 — **실제 요청과 같은 경로**로 DB 를 확인한다.

    `/` 는 앱 프로세스가 살아있는지만 본다. 2026-09-27 교착 장애에서
    DB 가 21분간 응답하지 않는데도 컨테이너는 healthy 였다
    (docs/postmortems/2026-09-27-db-pool-deadlock.md).

    ⚠️ 처음에는 NullPool 별도 엔진 + async def 로 만들었으나 **교착을 못 잡았다**
    (재현 검증: 60 req/s × 60s 과부하 시 교착 중에도 200·0.02초 응답).

      - 별도 엔진  → 막힌 **운영 풀**을 우회해 "DB 는 살아있다" 고 답함
      - async def → **스레드풀**도 거치지 않음

    교착은 DB 가 죽은 게 아니라 앱 안쪽(스레드풀 + 운영 풀)이 막힌 상태다.
    그래서 헬스체크도 그 둘을 똑같이 거쳐야 한다:

      - `def` (async 아님) → 스레드풀을 거친다
      - `SessionLocal()`   → 운영 풀에서 연결을 받는다

    교착 중에는 스레드도 연결도 못 받아 헬스체크 타임아웃(5초)에 걸려 unhealthy 가 된다.
    DB 다운도 운영 풀의 연결 실패로 잡힌다 — 판정이 pool_timeout(30초)만큼 늦어질 수
    있지만 헬스체크 타임아웃 5초가 먼저 끊으므로 결과는 같다.
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logging.getLogger(__name__).error("헬스체크 실패 — DB 응답 없음: %s", exc)
        return JSONResponse(status_code=503, content={"status": "unhealthy", "db": "down"})
    finally:
        db.close()
    return JSONResponse(content={"status": "ok", "db": "up"})


@app.get("/")
async def root():
    return JSONResponse(
        content={"message": "서간표 통합 서버가 준비되었습니다"},
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
