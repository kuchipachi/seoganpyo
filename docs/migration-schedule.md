# 마이그레이션 실행 일정

> 상세 근거는 [cloud-migration-plan.md](./cloud-migration-plan.md) (§ 번호는 그 문서 기준).
> 실제 인프라 구성값·설계 근거는 [aws-infra-design.md](./aws-infra-design.md),
> ECR·IAM 권한 설계는 [aws-ecr-iam-design.md](./aws-ecr-iam-design.md).
> 이 파일은 **매일 열어 보는 체크리스트**입니다.
>
> **D는 실작업일**이지 달력 날짜가 아닙니다. 하루에 못 끝내면 그 D가 이틀이 됩니다.

🟦 **하연** — 클라우드 인프라·보안·운영 자동화  🟩 **민지** — 앱·컨테이너·관측  🟪 **페어**

---

## 한눈에 보기

| 구간 | D | 🟦 하연 | 🟩 민지 |
| --- | --- | --- | --- |
| 1차 | D1~D10 | 5.25일 | 8.0일 |
| 2차 | D11~D16 | 5.5일 | 3.0일 (+선택 0.5) |
| **계** | **~16 D** | **10.75일** | **11.0일** |

**1차 완료 = 포트폴리오에 쓸 수 있는 상태.** 여기서 멈춰도 결과가 남습니다.

> 🔀 작업 레포: **`kuchipachi/seoganpyo`** — 원본 `gibunijjaejo/Opensource_Project`는 나머지 2명을 위해 그대로 둡니다.
>
> 💰 **크레딧 $120 → 활동 완료 시 $200 / 6개월 기한(≈ 2027-03)**. 상시 가동 시 월 ~$34입니다. $200을 채우고 RDS 중지 전략을 쓰면 6개월 기한까지 버팁니다(§2.1). 기한이 지나면 **Paid로 전환하지 않는 한 계정이 폐쇄되고 서비스가 내려갑니다.**

---

# 1차 — "돌아가고, 보이고, 알림이 온다"

## D1

### 🟦 하연 — AWS 기초 ✅ 완료

- [x] AWS 계정 생성 (하연 명의, 2026-09) — 크레딧 $120
- [x] 루트 계정 MFA
- [x] Budgets 알람 $1
- [x] IAM 사용자 2개(하연/민지) + 관리자 그룹
- [x] 리전 서울 `ap-northeast-2` 고정
- [x] VPC + 퍼블릭 서브넷 (NAT 금지)
- [x] IAM Deny 정책 `SeoganpyoDenyCostly` → ⚠️ **D2에 Multi-AZ 조건 보강 필요**

### 🟩 민지 — 레포 분리 + loadtest 분리 ✅ 완료

- [x] 새 org `kuchipachi` → 레포 `kuchipachi/seoganpyo` (Public, fork 아님)
- [x] `clone --bare` → `push --mirror` (main·dev + 태그 5개, 해시 일치 확인)
- [x] 워크플로 7개 자동 트리거 비활성화 — PR #1 머지
- [x] 하연 org Owner 초대 + 새 remote URL 공유
- [x] Actions 다시 켜기 + `main`/`dev` 브랜치 보호 (PR 필수, 승인 0명)
- [x] `chore/loadtest-compose` — JMeter/InfluxDB를 `docker-compose.loadtest.yml`로 분리 (`make loadtest-up` / `make jmeter-run`, 결과 조회 Grafana :3002)

---

## D2

### 🟦 하연 — RDS (0.5일)

- [x] 👉 로컬 remote 교체 — `origin`=`kuchipachi/seoganpyo`, 기존 포크는 `old-origin`
- [~] **Deny 정책 보강** — 불필요 판정. 무료 플랜이 RDS 템플릿을 **프리 티어로 고정**해
      Multi-AZ 선택 자체가 불가능하다. ALB/NAT 차단은 이미 적용됨(§2.1)
- [x] RDS 서브넷 그룹 — Default VPC 기본값 사용 (4 서브넷 / 4 AZ)
- [x] 보안그룹 **`SG-web`** `sg-095b42d816c449f1b` (80/443 → 0.0.0.0/0, 22 → 본인 IP)
- [x] 보안그룹 **`SG-rds`** `sg-0523ae10013431731` (5432 ← SG-web **그룹 참조**)
      ⚠️ 최초 **시드니 리전**에 만들어 재생성 — 포스트모템 1호 후보 (§8.4)
- [x] 태깅 `Project=seoganpyo / Env=prod / Owner=hayeon` (SG 2개) — RDS는 생성 시 적용
- [x] **RDS 생성** — `seoganpyo-db.czuy88iog7v8.ap-northeast-2.rds.amazonaws.com:5432` VPC `vpc-009480d192b44ba23`, SG `SG-rds`, 퍼블릭 액세스 아니요
      ⚠️ **무료 플랜 제약 2건**: 템플릿이 **프리 티어 고정**(Multi-AZ 선택 불가 — 오히려 안전),
      **백업 보존 최대 1일** → §2.5 백업 훈련은 **수동 스냅샷** 방식으로 변경
- [x] 👉 **민지에게 엔드포인트 전달** — DB 접속 정보 + SSH 키
- [x] 도메인 확정 — **`<EC2_IP>.nip.io`** (Route 53 미사용, 비용 0)

> 💡 RDS 생성에 10~15분 걸립니다. 그동안 §12 아키텍처 결정 기록을 시작하세요.
> 💡 RDS를 만들면 온보딩 크레딧 +$20.

### 🟩 민지 — 코드 정리 + Ollama (1.0일)

- [x] `chore/remove-school-server-refs` — `163.239.x` 제거, 레거시 삭제, `observability.server.yml` 삭제, CLAUDE.md "Groq" → Ollama 정정 (§6) — #5
- [x] `refactor/ollama-url-env` — `OLLAMA_URL`/`OLLAMA_MODEL`/`OLLAMA_TIMEOUT` 환경변수화, 연결 실패 시 503 "요약 준비 중입니다" (§4.3 B) — #7
- [x] (추가) `fix/syllabus-summarize-auth` — 인증 없던 `POST /syllabus/summarize` 로그인 필수 — #8
- [x] 👉 `.env` 필요 키 목록 정리 (§2.4) — [env-reference.md](./env-reference.md), #9

---

## D3

### 🟦 하연 — EC2 + Caddy (1.0일)

- [x] EC2 `t3.micro` `i-0cf5fbf562ec4017b` + EIP `<EC2_IP>` + 태그
- [x] **swap** — AL2023 기본 1.5Gi 사용 (RAM 913Mi + swap 1.5Gi)
- [x] Docker + Compose v5.5.1 설치 (`docker ps` sudo 없이 동작)
- [x] **RDS 연결 검증** — EC2 → RDS `psql` 성공, TLSv1.3 ✅ (§aws-infra-design 검증 결과)
- [x] Caddy 리버스 프록시 — `<EC2_IP>.nip.io` Let's Encrypt 자동 HTTPS ✅
      ⚠️ 경로 나열 방식이 `/auth` `/history` `/upload` 를 빠뜨려 로그인 전체가 막혔다
      → `/backend/*` 단일 prefix 로 통합 (포스트모템 1호)
- [x] 👉 **민지에게 SSH 접속 정보 전달** (터널용)

> 💡 EC2를 만들면 온보딩 크레딧 +$20.

### 🟩 민지 — Grafana 부재 대응 + Docker 최적화 시작 (1.0일)

- [x] `fix/monitoring-page-no-grafana` — iframe 조건부 숨김 + `query_prometheus`·`get_container_status` 조건부 등록, docker ps 오답 버그 수정 (§8.1) — #10
- [x] **before 측정** — `docker images` 3개 크기 + 빌드 시간 기록
- [x] `chore/slim-docker-images` — docker-cli 스테이지 제거, `.dockerignore` 정식 커밋(없으면 frontend 빌드 실패) — #11

---

## D4

### 🟦 하연 — ECR + 인스턴스 역할 (0.5일)

- [x] ECR 리포 3개 + 수명주기(최근 3개) + `scanOnPush` — [설계](./aws-ecr-iam-design.md)
- [x] EC2 역할 `SeoganpyoEC2Role` — ECR ReadOnly + SSM Core, `docker login` 성공 ✅
- [x] 민지 `SeoganpyoECRPush` — 리포 3개 한정 push 권한
- [x] 👉 민지에게 ECR URI 전달
- [x] 남는 시간: 아키텍처 결정 기록

### 🟩 민지 — 이미지 마무리 + 데이터 적재 시작 (1.0일)

- [x] **after 측정** → [performance.md](./performance.md) 📊 수치 1호: api 121.5 → 102.3 MB (−15.8%), 빌드 52 → 36s
- [x] 메모리 예약 하향 (backend 256M / frontend 256M / ocr 192M) + `NODE_OPTIONS=--max-old-space-size=256` — #14 `docker-compose.prod.yml` 에 반영 (🟦 하연)
- [x] **`docker buildx build --platform linux/amd64 ... --push`** 로 ECR에 3개 push — 태그 `baeac8c`(dev) + `latest`
  - ECR 크기: api 91.9 MB / ocr 67.4 MB / frontend 64.5 MB · frontend 빌드 인자 `NEXT_PUBLIC_API_URL=https://<EC2_IP>.nip.io`, Grafana 비움
  - ⚠️ scanOnPush: CRITICAL api·ocr 4건(Debian perl·openssl), frontend 3건(Alpine openssl) — 전부 **베이스 이미지 OS 패키지**, 별도 작업으로 갱신
- [x] **SSH 터널로 RDS 접속** — `ssh -L 5432:<rds>:5432 ec2-user@<ec2>` ⚠️ 로컬 PostgreSQL 이 5432 를 쓰면 터널 대신 로컬 DB 에 붙음 → 로컬 PG 중지
- [x] 스키마 생성 (테이블 20개)
- [x] `scripts/migrations/` 6개 검토 (§3.1) — RDS 스키마와 대조, 적용할 SQL 없음 (#17, `scripts/migrations/README.md`)

> 🔴 **강의 엑셀이 있는지 여기서 판명납니다.** 없으면 더미 시드 스크립트로 전환 (+2~3일).

---

## D5

### 🟪 첫 배포 (페어)

- [x] 🟦 EC2에 `.env` 배치 (`chmod 600`) — 1차는 평문, 2차 SSM
- [x] 🟦 **운영 compose·Caddy 추가** — base 가 `build:` 전제라 `pull` 실패 → `docker-compose.prod.yml` + `Caddyfile` 신규 (#14)
- [x] 🟦 ECR 로그인 → `pull && up -d` — 컨테이너 5개 전부 healthy
- [x] 🟪 **HTTPS 접속 확인** — https://<EC2_IP>.nip.io ✅ Let's Encrypt 자동 발급, TLS 1.3
- [x] OOM 없음 — 예약 832MiB / 가용 913MiB 로 하향한 덕분 (포스트모템 없음)

> 📌 **1차 배포 완료 (2026-09-24)** — 기동 시간 redis 12s → ocr 12s → api 43s → frontend 74s → caddy
>
> ⚠️ 배포 직후부터 **자동 취약점 스캐너 트래픽** 유입 (`/bundle.js`, `/app.bundle.js` 등 404).
> 공개 IP 서비스의 정상적인 현상이나, §8.3 알람 룰에 **4xx 급증**을 넣어 탐지할 것.

### 🟩 민지 — 데이터 적재 마무리 (1.0일)

- [x] 교수 크롤링 (`crawl_and_upsert`) — 전임 25명 상세·AI 연구요약 ⚠️ DB 에 있는 교수만 갱신하므로 시드가 먼저
- [x] 강의 데이터 적재 — 엑셀 없음 → **강의계획서 PDF 시드** (tracks 14 / 교수 28 / 강의 37, 2026-1 전공 27과목) — #12
- [x] ~~`e2e_seed_user.py` 테스트 계정~~ → **운영 DB 에는 넣지 않음** (공개 레포에 비밀번호가 있는 계정 + 가짜 강의). 시연 계정은 정상 가입·승인으로
- [x] **RDS 연결 풀** — `pool_pre_ping` ✅, `max_connections` = 79 ✅, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_TIMEOUT` 환경변수화 (#17)
- [x] 강의계획서 사전 요약 (§4.3 A) — 37/37, PDF별 정확한 강의에 저장 (`--summarize`) ⚠️ 트랙 분류가 AI 로 편향(26/35)

---

## D6

### 🟩 민지 — 베이스라인 측정 (0.5일) ★

- [x] **민지 PC에서** 부하 생성 — 도구를 **JMeter → k6**(open model, M1 네이티브)로 교체 (#20)
- [x] **반복 측정** — load 5 · stress 3 · breakpoint 1회 → 중앙값 [최소–최대], 노이즈 범위 17ms
- [x] RPS / p95 / 에러율 → [performance.md §3](./performance.md) — load API p95 **283ms [279–296]**, 기준 만족 최대 **33 RPS**
- [x] 부하와 같은 시간대에 서버 지표 수집 (vmstat·docker stats·pg_stat_activity·OOM) — 병목 **CPU 1코어 포화**, 메모리 아님
- [x] breakpoint 후 **21분 무응답 교착** 발견 → 로컬 재현·원인 규명 → [포스트모템](./postmortems/2026-09-27-db-pool-deadlock.md)

> 📊 **개선 수치의 기준점입니다.** 튜닝 전에 반드시 재 두세요. 편차 폭을 모르면 "p95 4.2 → 3.9초"가 개선인지 노이즈인지 판단할 수 없습니다.

### 🟦 하연 — D7 준비

- [x] 모니터링 명령 준비 — `scripts/ec2-monitor.sh` (런북 §6.2)
- [x] `docs/postmortems/` 디렉터리 생성 — 1호: [Caddy 백엔드 라우팅 누락](./postmortems/2026-09-26-caddy-backend-routing.md)
- [~] Discord 알림 → **D9 로 이동**. 1차엔 알람 발신원이 없어 쓸 곳이 없음.
      가입 알림(`DISCORD_SIGNUP_WEBHOOK`)은 **제거** — 관리자 본인이 `/admin/users` 를 직접 확인 (포폴 용도)
- [~] 아키텍처 결정 기록 — D10 항목으로 일원화 (아래)

---

## D7~D8 — 튜닝 (측정 기반 재계획) ★

> 원래 "RAM 튜닝(swap·커널·메모리 한도)"이었으나 **베이스라인 결과 병목은 메모리가 아니었다** —
> CPU 1코어 포화 · 요청당 SQL 64개 · 스레드풀·DB 풀 교착. 분담과 근거는 [계획서 §12 튜닝](./cloud-migration-plan.md).
> 규칙: **한 번에 하나씩 배포** · 측정 중 EC2 변경 금지 · 배포 뒤 `scripts/smoke-test.sh`

### 🟩 민지 — T1 · T2 (코드 + 측정)

- [x] **T1 동시 처리 한도** — 앱 미들웨어 `MAX_CONCURRENT_REQUESTS=14` (#27). 운영 측정 ✅ — 과부하 후 중단 21분 → 0분, 한계 이후 처리량 붕괴(51 → 12 RPS) → 약 54 RPS 유지, 평상시 성능 변화 없음
- [x] **T2 N+1 제거** — `selectinload` 로 SQL 64 → 3 (#29). 운영 측정 ✅ — 기준 만족 처리량 33 → 68 RPS, 최대 성공 처리량 54 → 100 RPS, 평상시 API p95 283 → 134ms
- [x] **포스트모템 1호** — [스레드풀·DB 풀 교착](./postmortems/2026-09-27-db-pool-deadlock.md) (가설 반증 → 수정 → 검증)
- [x] 포스트모템 2호 — [재현 데이터가 가벼워 처리량을 부풀려 잰 일](./postmortems/2026-09-28-light-repro-payload.md)

### 🟦 하연 — T3 · 배포 · 인스턴스 검증

- [x] **T3 DB 헬스체크 + autoheal** — #22 배포, 장애 주입 훈련(DB 네트워크 차단 → 97초 unhealthy → autoheal 17초 개입)
- [x] **T3 후속 수정** — #24 배포 완료. 별도 NullPool + `async def` 가 **앱 안쪽(스레드풀·운영 풀)을 우회**해 교착을 못 잡았다.
      실제 요청과 같은 경로(sync `def` + 운영 풀)로 변경 → 🟩 실측: 교착 시작~복구 **21분 → 약 50초** ([performance.md §4.1](./performance.md))
- [x] **T1 운영 배포** (`MAX_CONCURRENT_REQUESTS=14`) + 스모크 테스트 ✅
- [x] **T2 운영 배포** (`selectinload`) + 스모크 테스트 ✅ — 2026-09-29, 측정 전 CPU 크레딧 288(만충)
- [x] **배포 스크립트 2개** — 맥북 `scripts/build-push.sh` / EC2 `scripts/deploy.sh` (런북 §6.4)
      ECR 토큰 12시간 만료·`--platform` 누락·Caddy 재시작 누락이 반복돼 스크립트로 고정
- [x] **포스트모템 2건 완료** — [Caddy 라우팅 누락](./postmortems/2026-09-26-caddy-backend-routing.md), [헬스체크·자동복구 검증](./postmortems/2026-09-27-healthcheck-failover-drill.md)

### 🟪 페어 — T4 · 최종 측정

- [ ] **T4 uvicorn 워커 2개** — 🟩 부하 측정 / 🟦 메모리(913MB)·swap·CPU 크레딧 검증 → 처리량 vs 자원 트레이드오프 기록
- [ ] **최종 측정** — 베이스라인과 같은 조건 (load 5 · stress 3 · breakpoint 3) → Mann-Whitney U + 부트스트랩 CI 로 전후 비교

> 📊 **수치 2호**: "기준 만족 최대 처리량 33 → N RPS, 과부하 후 복구 21분 → 0초, 강의 목록 p95 X → Y ms"

---

## D9~D10 — 관측 · 알람

### 🟩 민지 — Grafana Cloud (1.5일) + 알람 룰 (0.5일)

- [x] **D9** Grafana Cloud 계정 → **Alloy** 컨테이너 추가 (#42, 옵트인 `COMPOSE_PROFILES=obs`) — 최대 부하 중 가용 300MB+ 실측 후 추가. 운영 1주 실측 **71MB**(한도 160M), 재시작 0
- [x] **D9** Docker 로그 + `backend:8000/metrics` → remote write — 1주간 메트릭 약 443만 샘플·로그 약 21.7만 줄, **실패 0** (10/08 확인). 값은 SSM `GRAFANA_CLOUD_*`
- [x] **D10** 대시보드 JSON 2개 임포트 → **datasource uid 교체** (`grafanacloud-logs`/`-prom`) — `scripts/grafana_cloud_sync.py` 로 레포 → Cloud 반영
- [ ] **D10** iframe 섹션 복구 (Public dashboard URL) + 프론트 재빌드·push
- [x] **D10** Grafana Alerting 룰 4개 — 5xx 비율, p95, API 다운, autoheal 재시작 → Discord (테스트 알림 확인)

### 🟦 하연 — CloudWatch + Discord (0.5일)

- [x] **D9** Discord 운영 알람 채널 + 웹훅 → SNS → Lambda 파이프라인, 테스트 발송 확인 ✅
- [x] **D9** CloudWatch 알람 4개 — EC2 상태검사 / **CPU 크레딧** / RDS 연결 수 / RDS 여유 메모리
      `infra/lambda/alarm-to-discord/` (멱등 배포 스크립트)
      ⚠️ urllib 은 User-Agent 가 없으면 Discord 앞단 Cloudflare 가 403 차단 (error code 1010)
- [x] **D9** 알림 경로 검증 — `set-alarm-state` 로 강제 ALARM/OK → Discord 🔴/🟢 수신 확인
- [x] **D9** autoheal 재시작 루프 방지 — `scripts/autoheal-guard.sh` (cron 5분)
      검증: 임계를 낮춰 실제 발동 → 감지·스냅샷·autoheal 중지·Discord 알림 4단계 확인
- [ ] **D9 (선택)** 실제 지표로 알람 발동 검증 — EC2 잠시 중지 → `StatusCheckFailed`
      ⚠️ **T3 재현(DB 차단)으로는 검증 불가.** DB 를 끊어도 EC2 는 정상이고 RDS 연결 수는
      오히려 줄어 CloudWatch 알람 4개 중 아무것도 울리지 않는다.
      컨테이너 헬스체크 장애는 CloudWatch 관할이 아니다 → Grafana 5xx 룰(🟩 D10)·guard 담당
- [x] **D10** 아키텍처 결정 기록 — [`docs/adr.md`](./adr.md) (결정 17건: 비용 5 · 보안 8 · 운영 4)

---

## ✅ 1차 완료 기준

- [x] HTTPS로 서비스 접속됨 — https://<EC2_IP>.nip.io
- [x] Grafana 대시보드에 로그·메트릭이 보임 (🟩 D9~D10) — Grafana Cloud `서간표` 폴더
- [x] 알람이 Discord로 옴 — **CloudWatch ✅** (인프라) / **Grafana ✅** (앱: 5xx·p95·다운·재시작)
- [~] `docs/performance.md` — 이미지 크기 ✅ · 베이스라인 ✅ / **튜닝 후 수치는 T1~T4 이후**
- [x] `docs/postmortems/`에 4건+ — 🟦 2건(Caddy 라우팅·헬스체크 훈련) / 🟩 2건(교착·재현 데이터 측정 결함)
- [x] 아키텍처 결정 기록 — [`docs/adr.md`](./adr.md)

---

# 2차 — 자동화·스토리지·운영 문서

## 🟦 하연 — CI/CD (D11~D16) ★ 최난도

- [x] **D11** SSM Parameter Store — `.env` 이관 완료
  - `scripts/ssm-put-params.sh` (1회 등록) / `scripts/ssm-fetch-env.sh` (배포 시 조회)
  - 비밀 10개는 **SecureString**(KMS 암호화), 나머지는 String — 분류는 `env-reference.md` 기준
  - EC2 인스턴스 역할에 `SeoganpyoSSMReadParams` — **경로 `/seoganpyo/prod/*` 한정**,
    `kms:Decrypt` 는 `ViaService: ssm` 조건으로 SSM 경유일 때만
  - `deploy.sh` 가 기동 전에 SSM 에서 받아옴 → **값 변경 시 EC2 에 들어갈 필요 없음**
  - ⚠️ `.env` 파일 자체는 남는다 — compose 가 `env_file` 로 읽어야 하므로.
    SSM 의 이점은 **저장소 암호화 + 값 배포 중앙화**이지 EC2 평문 제거가 아니다
  - 빈 값 5개(`PROMETHEUS_URL`·`DEFECTDOJO_*`·`NEXT_PUBLIC_GRAFANA_URL`)는 등록하지 않음 —
    compose 가 `${VAR:-}` 로 기본값을 주므로 결과 동일
- [x] **D11~D13** **GitHub OIDC + IAM 신뢰 정책** — AWS 쪽 설정 완료
  - OIDC 자격 증명 공급자 등록 (`token.actions.githubusercontent.com`)
  - `SeoganpyoGitHubActionsRole` + 신뢰 정책 — `sub` 를 **`dev`·`main` 두 브랜치로 한정**
    (계획 원안은 `main` 만이었으나 팀이 `dev` 에 머지하므로 둘 다 허용)
  - 권한: `SeoganpyoECRPush`(리포 3개) + `SeoganpyoSSMDeploy`(인스턴스 ID 한정)
  - ⚠️ **SSM Agent 가 등록돼 있지 않았다** — 인스턴스 역할에 `AmazonSSMManagedInstanceCore`
    가 빠져 있었고, 정책 추가 후에도 Agent 가 캐시된 자격증명을 물고 27분 재시도 대기에
    들어갔다. 정책 부착 → **IAM 전파 대기 → Agent 재시작** 순서가 필요
- [x] **D14~D15** SSM Run Command 배포 — `.github/workflows/deploy.yml` **실행 검증 완료** ✅
  - OIDC 인증 → ECR 빌드·push(`latest` + `github.sha`) → SSM 으로 `deploy.sh` → 외부에서 최종 확인
  - `github.sha` 태그를 같이 다는 이유: **롤백** (ECR 수명주기 3개 보존 → 직전 2개까지)
  - 마지막 검증을 러너(외부)에서 하는 이유: EC2 내부 스모크로는 Caddy·인증서 경로를 못 본다
    (포스트모템 1호가 정확히 그 차이에서 발생)
  - 자동 트리거는 주석 처리 — T1~T4 튜닝 중에는 한 번에 하나씩 배포해야 효과 구분 가능
- [x] **🔒 보안그룹 22번 포트 폐쇄** — SSH 없이 배포되므로. 서버 접속은 Session Manager
  - 동적 IP 때문에 보안그룹을 계속 갱신하던 문제도 함께 해소
- [x] 정리 — 디버그 브랜치 삭제, 불필요한 `AWS_ACCOUNT_ID` Secret 제거

> **막혔던 것 3가지** (설계 문서에 상세)
>
> 1. **`sub` 에 org/repo ID 가 삽입된다** — `repo:kuchipachi@<orgID>/seoganpyo@<repoID>:ref:...`
>    문서 예제는 `repo:org/repo:ref:...` 형식이라 계속 불일치. 신뢰 정책·공급자·`aud` 를
>    다 확인해도 정상이었고, **워크플로에서 토큰을 직접 출력한 뒤에야** 원인이 드러났다
> 2. **Secret 에 비밀 아닌 값(계정 ID)을 넣어 디버깅 불가** — 로그에 `***` 로 가려져
>    값 확인이 안 됐다. 실제 방어선은 `sub` 조건이므로 ARN 을 직접 지정
> 3. **CI 빌드 컨텍스트가 로컬과 다르다** — `.gitignore` 로 `static/` 이 추적되지 않아
>    러너에서 `COPY ./static` 실패. 로컬은 폴더가 있어 계속 성공했다
- [~] **D15** **비용 분석** — **T4 전 스냅샷 완료** ([performance.md §5](./performance.md))
      일 평균 $0.874 · 월 환산 $26.22 · 잔액 약 $113 → 이 속도면 약 4.3개월 (6개월 기한보다 짧음)
      비중: **RDS 56.4%** / EC2 25.5% / 퍼블릭 IPv4 9.8% / EBS 8.1%
      ⚠️ `RECORD_TYPE` 에서 `Credit` 를 제외해야 실사용량이 보인다 (안 빼면 상쇄돼 0·음수)
      남은 것: **T4 후 재측정** → 처리량 vs 비용 트레이드오프, 절감 실험(RDS 중지), 만료 후 예상액
- [ ] **D16** 런북 — 배포 + **롤백**(이전 ECR 태그) (0.25일)

> ⚠️ 2차는 착수하자마자 **OIDC부터** 하세요. 막히면 시간이 필요합니다.
> → 실제로 `AssumeRoleWithWebIdentity` 로 **3회 실패**했다. 추측보다 토큰을 찍는 게 빨랐다.

## 🟩 민지 — 스토리지·운영 (D11~D13, +D16)

- [ ] **D11~D12** `feat/storage-s3` (1.5일) — `storage_service.py` 추상화, `boto3`를 `requirements.txt`에 추가, 최소 권한 IAM 정책 초안 → 👉 하연 검토
- [ ] **D12** **RDS 백업·복구 훈련** (0.5일) — 스냅샷 → 복원 → 검증 → **복원 인스턴스 즉시 삭제** ⚠️ 크레딧 2배 차감
- [ ] **D13** 관측 토큰 인증 (0.5일) — `query_prometheus` → Cloud Prometheus
- [ ] **D13 (선택)** RDS 자동 중지 — EventBridge + Lambda (0.5일, 온보딩 크레딧 +$20)
- [ ] **D14~D15** 여유 → 하연 OIDC·배포 테스트 지원, 비용 실험 측정 보조
- [ ] **D16** 런북 — 장애 확인 순서 + 접속 정보 (0.25일)

## D16 — 🟪 마무리

- [ ] README / 계획서 갱신, 포스트모템·결정 기록 정리 (각 0.25일)
- [ ] 워크플로 재활성화 여부 정리 (§13.1)
- [ ] **6개월 후 결정 일정** 캘린더 등록 — Paid 전환 / 종료 / 이전 (만료 1개월 전)

---

## 접점 — 상대를 기다리는 지점

| 시점 | 내용 |
| --- | --- |
| **D1 → D2** | 🟩 새 레포 URL·org 초대 → 🟦 로컬 remote 교체 |
| **D2 → D4** | 🟦 RDS 엔드포인트 → 🟩 데이터 적재 (**직렬**) |
| **D2 → D4** | 🟦 도메인 결정 → 🟩 프론트 빌드 (빌드 타임 환경변수) |
| **D3 → D4** | 🟦 EC2 SSH 정보 → 🟩 SSH 터널 (**직렬**) |
| **D4** | 🟦 ECR·push 권한 → 🟩 이미지 push |
| **D6 → D7** | 🟩 베이스라인 → 튜닝 T1~T4 (측정 없이 튜닝 금지) ✅ 베이스라인 완료 |
| **D2 → D11** | 🟩 `.env` 키 목록 → 🟦 SSM 등록 |
| **D12** | 🟩 S3 IAM 정책 초안 → 🟦 검토·적용 |

---

## 막히면

| 증상 | 조치 |
| --- | --- |
| 컨테이너가 자꾸 죽음 | `dmesg \| grep -i oom` → §2.2 |
| `exec format error` | arm64 이미지 — `buildx --platform linux/amd64`로 다시 빌드 |
| 강의 엑셀이 없음 | 더미 시드 스크립트로 전환 (+2~3일) |
| RDS 접속 안 됨 | SSH 터널 떠 있는지, `sg-rds`가 `sg-web`을 허용하는지 |
| OIDC 신뢰 정책 거부 | `sub` 조건의 레포·브랜치 문자열 확인 |
| Grafana 대시보드 빈 화면 | datasource uid 불일치 (§8.2-3) |
| 관리자 챗이 가끔 실패 | `query_prometheus` 조건부 등록 (§8.1) |
| 비용 알람이 옴 | ALB/NAT/Multi-AZ가 생겼는지 즉시 확인 (§2.1) |
| 크레딧이 빨리 줄어듦 | Cost Explorer 태그별 확인 → RDS 중지, 복원용 RDS 방치 여부 (§2.5) |
| 원본에 push할 뻔함 | `git remote -v` — `origin`이 `kuchipachi/seoganpyo`인지, `upstream` push가 `DISABLED`인지 |
