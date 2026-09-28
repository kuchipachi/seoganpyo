"""동시 처리 한도 미들웨어 (T1) — 넘치면 즉시 503, 헬스체크는 예외."""
import anyio
import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.concurrency import ConcurrencyLimitMiddleware


def _make_app(limit: int, gate: anyio.Event):
    async def slow(request):
        await gate.wait()          # 슬롯을 쥐고 대기
        return JSONResponse({"ok": True})

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    inner = Starlette(routes=[Route("/slow", slow), Route("/healthz", healthz)])
    return ConcurrencyLimitMiddleware(inner, limit=limit)


def test_sheds_when_full_and_exempts_healthcheck():
    async def scenario():
        gate = anyio.Event()
        app = _make_app(limit=1, gate=gate)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            results = {}

            async def first():
                results["first"] = await client.get("/slow")

            async with anyio.create_task_group() as tg:
                tg.start_soon(first)
                await anyio.sleep(0.05)                    # 첫 요청이 슬롯을 차지할 때까지
                assert app.active == 1

                busy = await client.get("/slow")           # 한도 초과 → 즉시 503
                assert busy.status_code == 503
                assert busy.headers["retry-after"] == "1"
                assert busy.json()["detail"]["code"] == "SERVER_BUSY"

                health = await client.get("/healthz")      # 헬스체크는 한도와 무관
                assert health.status_code == 200

                gate.set()                                  # 첫 요청 완료 → 슬롯 반납
            assert results["first"].status_code == 200
            assert app.active == 0
            assert (await client.get("/slow")).status_code == 200   # 다시 받음 (gate 열림)

    anyio.run(scenario)


def test_disabled_when_limit_zero():
    async def scenario():
        gate = anyio.Event()
        gate.set()
        app = _make_app(limit=0, gate=gate)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            assert (await client.get("/slow")).status_code == 200
            assert app.active == 0                          # 꺼져 있으면 세지도 않음

    anyio.run(scenario)


def test_root_path_is_stripped_for_exempt_check():
    mw = ConcurrencyLimitMiddleware(app=None, limit=1)
    assert mw._route_path({"path": "/backend/healthz", "root_path": "/backend"}) == "/healthz"
    assert mw._route_path({"path": "/healthz", "root_path": "/backend"}) == "/healthz"
    assert mw._route_path({"path": "/backend", "root_path": "/backend"}) == "/"
