COMPOSE         = docker-compose.yml
COMPOSE_DEV     = docker-compose.dev.yml
COMPOSE_OBS     = docker-compose.observability.yml

DC_DEV      = docker compose -f $(COMPOSE) -f $(COMPOSE_DEV)
DC_PROD     = docker compose -f $(COMPOSE)
DC_OBS      = docker compose -f $(COMPOSE) -f $(COMPOSE_DEV) -f $(COMPOSE_OBS)

# ── 로컬 개발 ─────────────────────────────────────────
dev:
	$(DC_DEV) up --build

down:
	$(DC_DEV) down

logs:
	$(DC_DEV) logs -f

ps:
	$(DC_DEV) ps

# Playwright e2e용 테스트 계정 시드 (멱등)
# 백엔드 컨테이너가 떠있어야 함 (make dev)
e2e-seed:
	$(DC_DEV) exec -T -e PYTHONPATH=/app backend python scripts/e2e_seed_user.py

# ── 프로덕션 배포 ──────────────────────────────────────
prod:
	bash scripts/pre-deploy.sh
	$(DC_PROD) up --build -d
	bash scripts/post-deploy.sh

prod-down:
	$(DC_PROD) down

prod-logs:
	$(DC_PROD) logs -f

# ── 관측 스택 (Loki + Promtail + Grafana) — 옵트인 ────
# 로컬 개발용 (make dev 위에 덧붙임)
up-obs:
	$(DC_OBS) up -d --build

down-obs:
	$(DC_OBS) down

logs-obs:
	$(DC_OBS) logs -f loki promtail grafana


# ── 부하 테스트 (JMeter → InfluxDB → Grafana) ──────────
# 부하 생성 PC 에서 실행 (측정 대상 서버에서 돌리지 말 것)
# 사용 예: make jmeter-run BASE_HOST=<EC2 IP> BASE_PORT=8000 THREADS=50 DURATION=120
# 운영(Caddy): make jmeter-run BASE_HOST=54.180.181.46.nip.io BASE_PORT=443 BASE_SCHEME=https API_PREFIX=/backend
# 결과는 http://localhost:3002 대시보드 "Apache JMeter — Load Test"에서 실시간 확인
DC_LOADTEST = docker compose -p loadtest -f docker-compose.loadtest.yml

loadtest-up:
	$(DC_LOADTEST) up -d influxdb grafana

loadtest-down:
	$(DC_LOADTEST) down

JMETER_FILE   ?= seoganpyo-smoke.jmx
BASE_HOST     ?= host.docker.internal
BASE_PORT     ?= 8000
BASE_SCHEME   ?= http
THREADS       ?= 20
RAMPUP        ?= 10
DURATION      ?= 60
TEST_NAME     ?= seoganpyo-smoke
API_PREFIX    ?=

jmeter-run:
	$(DC_LOADTEST) --profile jmeter run --rm jmeter \
		-n -t /tests/$(JMETER_FILE) \
		-l /results/$(TEST_NAME)-$(shell date +%Y%m%d-%H%M%S).jtl \
		-JBASE_HOST=$(BASE_HOST) -JBASE_PORT=$(BASE_PORT) -JBASE_SCHEME=$(BASE_SCHEME) \
		-JTHREADS=$(THREADS) -JRAMPUP=$(RAMPUP) -JDURATION=$(DURATION) \
		-JTEST_NAME=$(TEST_NAME) -JAPI_PREFIX=$(API_PREFIX) \
		-JINFLUX_URL=http://influxdb:8086/write?db=jmeter

jmeter-report:
	@ls -lt infra/loadtest/jmeter/results/*.jtl 2>/dev/null | head -5 || echo "결과 없음"

# ── 정적 분석 (SonarCloud) ──────────────────────────────
# 분석은 PR/push 시 GitHub Actions(.github/workflows/sonarcloud.yml)가 자동 실행.
# 로컬에서 수동 분석은 사용하지 않음 (SonarCloud SaaS 라 인스턴스 운영 부담 0).
# 결과는 https://sonarcloud.io/dashboard?id=<projectKey> + PR 코멘트로 표시.
