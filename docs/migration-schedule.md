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
- [ ] **Deny 정책 보강** — `rds:MultiAz`, `rds:DatabaseClass`, `ec2:InstanceType` 조건 (§2.1) → Multi-AZ 생성 시도로 거부 확인
- [ ] AZ가 다른 퍼블릭 서브넷 2개 → **RDS 서브넷 그룹**
- [x] 보안그룹 **`SG-web`** `sg-095b42d816c449f1b` (80/443 → 0.0.0.0/0, 22 → 본인 IP)
- [x] 보안그룹 **`SG-rds`** `sg-0523ae10013431731` (5432 ← SG-web **그룹 참조**)
      ⚠️ 최초 **시드니 리전**에 만들어 재생성 — 포스트모템 1호 후보 (§8.4)
- [x] 태깅 `Project=seoganpyo / Env=prod / Owner=hayeon` (SG 2개) — RDS는 생성 시 적용
- [x] **RDS 생성** — `seoganpyo-db.czuy88iog7v8.ap-northeast-2.rds.amazonaws.com:5432` VPC `vpc-009480d192b44ba23`, SG `SG-rds`, 퍼블릭 액세스 아니요
      ⚠️ **무료 플랜 제약 2건**: 템플릿이 **프리 티어 고정**(Multi-AZ 선택 불가 — 오히려 안전),
      **백업 보존 최대 1일** → §2.5 백업 훈련은 **수동 스냅샷** 방식으로 변경
- [x] 👉 **민지에게 엔드포인트 전달** — DB 접속 정보 + SSH 키
- [x] 도메인 확정 — **`54.180.181.46.nip.io`** (Route 53 미사용, 비용 0)

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

- [x] EC2 `t3.micro` `i-0cf5fbf562ec4017b` + EIP `54.180.181.46` + 태그
- [x] **swap** — AL2023 기본 1.5Gi 사용 (RAM 913Mi + swap 1.5Gi)
- [x] Docker + Compose v5.5.1 설치 (`docker ps` sudo 없이 동작)
- [x] **RDS 연결 검증** — EC2 → RDS `psql` 성공, TLSv1.3 ✅ (§aws-infra-design 검증 결과)
- [ ] Caddy 리버스 프록시 — `<ip>.nip.io` 자동 HTTPS 확인
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
- [ ] 메모리 예약 하향 (backend 256M / frontend 256M / ocr 192M) + `NODE_OPTIONS=--max-old-space-size=256` ← **D5 첫 배포 전 필수** (미완)
- [x] **`docker buildx build --platform linux/amd64 ... --push`** 로 ECR에 3개 push — 태그 `baeac8c`(dev) + `latest`
  - ECR 크기: api 91.9 MB / ocr 67.4 MB / frontend 64.5 MB · frontend 빌드 인자 `NEXT_PUBLIC_API_URL=https://54.180.181.46.nip.io`, Grafana 비움
  - ⚠️ scanOnPush: CRITICAL api·ocr 4건(Debian perl·openssl), frontend 3건(Alpine openssl) — 전부 **베이스 이미지 OS 패키지**, 별도 작업으로 갱신
- [x] **SSH 터널로 RDS 접속** — `ssh -L 5432:<rds>:5432 ec2-user@<ec2>` ⚠️ 로컬 PostgreSQL 이 5432 를 쓰면 터널 대신 로컬 DB 에 붙음 → 로컬 PG 중지
- [x] 스키마 생성 (테이블 20개)
- [ ] `scripts/migrations/` 6개 검토 (§3.1)

> 🔴 **강의 엑셀이 있는지 여기서 판명납니다.** 없으면 더미 시드 스크립트로 전환 (+2~3일).

---

## D5

### 🟪 첫 배포 (페어)

- [x] 🟦 EC2에 `.env` 배치 (`chmod 600`) — 1차는 평문, 2차 SSM
- [x] 🟦 **운영 compose·Caddy 추가** — base 가 `build:` 전제라 `pull` 실패 → `docker-compose.prod.yml` + `Caddyfile` 신규 (#14)
- [x] 🟦 ECR 로그인 → `pull && up -d` — 컨테이너 5개 전부 healthy
- [x] 🟪 **HTTPS 접속 확인** — https://54.180.181.46.nip.io ✅ Let's Encrypt 자동 발급, TLS 1.3
- [x] OOM 없음 — 예약 832MiB / 가용 913MiB 로 하향한 덕분 (포스트모템 없음)

> 📌 **1차 배포 완료 (2026-09-24)** — 기동 시간 redis 12s → ocr 12s → api 43s → frontend 74s → caddy
>
> ⚠️ 배포 직후부터 **자동 취약점 스캐너 트래픽** 유입 (`/bundle.js`, `/app.bundle.js` 등 404).
> 공개 IP 서비스의 정상적인 현상이나, §8.3 알람 룰에 **4xx 급증**을 넣어 탐지할 것.

### 🟩 민지 — 데이터 적재 마무리 (1.0일)

- [x] 교수 크롤링 (`crawl_and_upsert`) — 전임 25명 상세·AI 연구요약 ⚠️ DB 에 있는 교수만 갱신하므로 시드가 먼저
- [x] 강의 데이터 적재 — 엑셀 없음 → **강의계획서 PDF 시드** (tracks 14 / 교수 28 / 강의 37, 2026-1 전공 27과목) — #12
- [x] ~~`e2e_seed_user.py` 테스트 계정~~ → **운영 DB 에는 넣지 않음** (공개 레포에 비밀번호가 있는 계정 + 가짜 강의). 시연 계정은 정상 가입·승인으로
- [ ] **RDS 연결 풀** — `pool_pre_ping` ✅, `max_connections` = 79 확인 ✅, `pool_size` 설정 (미완)
- [x] 강의계획서 사전 요약 (§4.3 A) — 37/37, PDF별 정확한 강의에 저장 (`--summarize`) ⚠️ 트랙 분류가 AI 로 편향(26/35)

---

## D6

### 🟩 민지 — 베이스라인 측정 (0.5일) ★

- [ ] **민지 PC에서** `make jmeter-run BASE_HOST=<EC2 IP>` ← EC2에서 돌리지 말 것
- [ ] **같은 조건 3회 반복** → 중앙값 + 편차 폭 기록
- [ ] RPS / p95 / 에러율 → `docs/performance.md`
- [ ] 부하 중 `SELECT count(*) FROM pg_stat_activity;` 주기적으로 기록

> 📊 **개선 수치의 기준점입니다.** 튜닝 전에 반드시 재 두세요. 편차 폭을 모르면 "p95 4.2 → 3.9초"가 개선인지 노이즈인지 판단할 수 없습니다.

### 🟦 하연 — D7 준비

- [x] 모니터링 명령 준비 — `scripts/ec2-monitor.sh` (런북 §6.2)
- [x] `docs/postmortems/` 디렉터리 생성 — 1호: [Caddy 백엔드 라우팅 누락](./postmortems/2026-09-26-caddy-backend-routing.md)
- [~] Discord 알림 → **D9 로 이동**. 1차엔 알람 발신원이 없어 쓸 곳이 없음.
      가입 알림(`DISCORD_SIGNUP_WEBHOOK`)은 **제거** — 관리자 본인이 `/admin/users` 를 직접 확인 (포폴 용도)
- [ ] 아키텍처 결정 기록 계속

---

## D7~D8 — 🟪 RAM 튜닝 (페어, 각 1.25일) ★

**가장 어렵고 가장 배울 게 많은 구간입니다.** 둘이 같이 하세요.

### 🟦 하연 — 인스턴스 레벨

- [ ] swap 동작 확인, `vm.swappiness` 등 커널 파라미터
- [ ] `dmesg`로 OOM Killer 로그 추적
- [ ] **포스트모템** — 자기가 겪은 것 2건+

### 🟩 민지 — 컨테이너·앱 레벨

- [ ] 부하를 올리며 OOM 임계점 찾기
- [ ] 메모리 예약·제한 재조정, Node/Python 메모리 튜닝
- [ ] **부하 재측정 3회** → before/after 비교 (노이즈 범위 초과인지 판정)
- [ ] **포스트모템** — 자기가 겪은 것 2건+

> 📊 **수치 2호**: "동시 N명에서 5xx·OOM 재시작 → 튜닝 후 M명까지 5xx 0건, p95 X→Y초"
> ⚠️ OOM은 배포 몇 시간 뒤에 터지기도 합니다. 여유를 두세요.

---

## D9~D10 — 관측 · 알람

### 🟩 민지 — Grafana Cloud (1.5일) + 알람 룰 (0.5일)

- [ ] **D9** Grafana Cloud 계정 → **Alloy** 컨테이너 추가 (~100MB) — RAM 여유를 **실측한 뒤** 붙일 것
- [ ] **D9** Docker 로그 + `backend:8000/metrics` → remote write
- [ ] **D10** 대시보드 JSON 2개 임포트 → **datasource uid 교체** (`loki`/`prometheus` → Cloud uid)
- [ ] **D10** iframe 섹션 복구 (Public dashboard URL) + 프론트 재빌드·push
- [ ] **D10** Grafana Alerting 룰 — 5xx 급증, p95, 컨테이너 재시작

### 🟦 하연 — CloudWatch + Discord (0.5일)

- [ ] **D9** CloudWatch 알람 — EC2 상태 검사, CPU, RDS 연결 수·여유 스토리지
- [ ] **D9** Discord 운영 알람 채널 + 웹훅 생성 → SNS 연동, 테스트 알람 1회 발화
- [ ] **D10** 아키텍처 결정 기록 완성, 1차 완료 기준 점검

---

## ✅ 1차 완료 기준

- [ ] HTTPS로 서비스 접속됨
- [ ] Grafana 대시보드에 로그·메트릭이 보임
- [ ] 알람이 Discord로 옴 (Grafana·CloudWatch 각 1회 이상)
- [ ] `docs/performance.md`에 이미지 크기 + 튜닝 전후 수치
- [ ] `docs/postmortems/`에 4건+ (🟦 2건+, 🟩 2건+)
- [ ] 아키텍처 결정 기록 초안

---

# 2차 — 자동화·스토리지·운영 문서

## 🟦 하연 — CI/CD (D11~D16) ★ 최난도

- [ ] **D11** SSM Parameter Store — `.env` 전체 이관 (0.5일), EC2 `.env` 평문 제거
- [ ] **D11~D13** **GitHub OIDC + IAM 신뢰 정책** (2.5일) ← 여기서 막힘
  - `sub` 조건: `repo:kuchipachi/seoganpyo:ref:refs/heads/main`
  - 레포에 AWS 키를 두지 않는 구조
- [ ] **D14~D15** SSM Run Command 배포 (1.5일) — `deploy.yml`, SSH 없이 배포 → 22번 포트 닫기
- [ ] **D15** **비용 분석** (0.5일) — Cost Explorer, 크레딧 고갈 예상일, 만료 후 예상액, 절감 실험 (📊 수치 3호)
- [ ] **D16** 런북 — 배포 + **롤백**(이전 ECR 태그) (0.25일)

> ⚠️ 2차는 착수하자마자 **OIDC부터** 하세요. 막히면 시간이 필요합니다.

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
| **D6 → D7** | 🟩 베이스라인 → 🟪 RAM 튜닝 (측정 없이 튜닝 금지) |
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
