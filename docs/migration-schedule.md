# 마이그레이션 실행 일정

> 상세 근거는 [cloud-migration-plan.md](./cloud-migration-plan.md) (§ 번호는 그 문서 기준).
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

- [ ] 👉 민지에게서 받은 URL로 로컬 remote 교체 (§13)
- [ ] **Deny 정책 보강** — `rds:MultiAz`, `rds:DatabaseClass`, `ec2:InstanceType` 조건 (§2.1) → Multi-AZ 생성 시도로 거부 확인
- [ ] AZ가 다른 퍼블릭 서브넷 2개 → **RDS 서브넷 그룹**
- [ ] 보안그룹 `sg-web`(80/443 + 팀원 IP만 22), `sg-rds`(sg-web에서만 5432)
- [ ] 태깅 `Project=seoganpyo / Env=prod / Owner=hayeon`
- [ ] **RDS 생성** — 체크리스트 §2.5 (개발/테스트 템플릿, `db.t4g.micro`, Multi-AZ·자동 조정·퍼블릭 액세스·Performance Insights 전부 끄기)
- [ ] 👉 **민지에게 엔드포인트 전달**
- [ ] 도메인 결정 (기본 `nip.io`) → 👉 민지에게 전달

> 💡 RDS 생성에 10~15분 걸립니다. 그동안 §12 아키텍처 결정 기록을 시작하세요.
> 💡 RDS를 만들면 온보딩 크레딧 +$20.

### 🟩 민지 — 코드 정리 + Ollama (1.0일)

- [ ] `chore/remove-school-server-refs` — `163.239.x` 제거, 레거시 삭제, `observability.server.yml` 삭제, CLAUDE.md "Groq" → Ollama 정정 (§6)
- [ ] `refactor/ollama-url-env` — `OLLAMA_URL`/`OLLAMA_TIMEOUT` 환경변수화(2개 파일), 실패 시 503 "요약 준비 중입니다" (§4.3 B)
- [ ] 👉 `.env` 필요 키 목록 정리 (§2.4) — 하연 2차 SSM 등록용

---

## D3

### 🟦 하연 — EC2 + Caddy (1.0일)

- [ ] EC2 `t3.micro` 기동 + Elastic IP + 태그
- [ ] **swap 2GB** (`/etc/fstab` 등록까지) (§2.2)
- [ ] Docker + Compose 설치
- [ ] Caddy 리버스 프록시 — `<ip>.nip.io` 자동 HTTPS 확인
- [ ] 👉 **민지에게 SSH 접속 정보 전달** (터널용)

> 💡 EC2를 만들면 온보딩 크레딧 +$20.

### 🟩 민지 — Grafana 부재 대응 + Docker 최적화 시작 (1.0일)

- [ ] `fix/monitoring-page-no-grafana` — iframe 조건부 숨김 + `query_prometheus` 조건부 등록 (§8.1)
- [ ] **before 측정** — `docker images` 3개 크기 + 빌드 시간 기록
- [ ] `chore/slim-docker-images` — docker-cli 스테이지 제거, 멀티스테이지·레이어 캐싱 점검

---

## D4

### 🟦 하연 — ECR + 인스턴스 역할 (0.5일)

- [ ] ECR 리포지토리 3개 (`seoganpyo-api` / `-frontend` / `-ocr`) + 수명주기 정책(최근 3개)
- [ ] EC2 인스턴스 역할 — `AmazonEC2ContainerRegistryReadOnly`
- [ ] 민지 IAM 사용자 — 3개 리포지토리 push 권한만
- [ ] 👉 민지에게 ECR URI 전달
- [ ] 남는 시간: 아키텍처 결정 기록

### 🟩 민지 — 이미지 마무리 + 데이터 적재 시작 (1.0일)

- [ ] **after 측정** → `docs/performance.md` (📊 수치 1호: "3개 합계 X MB → Y MB")
- [ ] 메모리 예약 하향 (backend 256M / frontend 256M / ocr 192M) + `NODE_OPTIONS=--max-old-space-size=256`
- [ ] **`docker buildx build --platform linux/amd64 ... --push`** 로 ECR에 3개 push ← Apple Silicon 주의
- [ ] **SSH 터널로 RDS 접속** — `ssh -L 5432:<rds>:5432 ec2-user@<ec2>`
- [ ] 스키마 생성 확인, `scripts/migrations/` 6개 검토 (§3.1)

> 🔴 **강의 엑셀이 있는지 여기서 판명납니다.** 없으면 더미 시드 스크립트로 전환 (+2~3일).

---

## D5

### 🟪 첫 배포 (페어)

- [ ] 🟦 EC2에 `.env` 배치 (`chmod 600`) — 1차는 평문, 2차 SSM
- [ ] 🟦 ECR 로그인 → `docker compose pull && up -d`
- [ ] 🟪 HTTPS 접속·헬스체크 확인
- [ ] OOM 등이 터지면 → 겪은 사람이 **포스트모템** (§8.4)

### 🟩 민지 — 데이터 적재 마무리 (1.0일)

- [ ] 교수 크롤링 (`crawl_and_upsert`)
- [ ] 강의 데이터 적재 (`import_courses.py` 또는 더미 시드)
- [ ] `e2e_seed_user.py` 테스트 계정
- [ ] **RDS 연결 풀** — `pool_pre_ping`, `max_connections`(~80) 확인 후 `pool_size` 설정
- [ ] (시간 되면) 강의계획서 배치 사전 요약 (§4.3 A)

---

## D6

### 🟩 민지 — 베이스라인 측정 (0.5일) ★

- [ ] **민지 PC에서** `make jmeter-run BASE_HOST=<EC2 IP>` ← EC2에서 돌리지 말 것
- [ ] **같은 조건 3회 반복** → 중앙값 + 편차 폭 기록
- [ ] RPS / p95 / 에러율 → `docs/performance.md`
- [ ] 부하 중 `SELECT count(*) FROM pg_stat_activity;` 주기적으로 기록

> 📊 **개선 수치의 기준점입니다.** 튜닝 전에 반드시 재 두세요. 편차 폭을 모르면 "p95 4.2 → 3.9초"가 개선인지 노이즈인지 판단할 수 없습니다.

### 🟦 하연 — D7 준비

- [ ] 모니터링 명령 준비 (`docker stats`, `free -h`, `dmesg | grep -i oom`)
- [ ] `docs/postmortems/` 디렉터리 생성
- [ ] Discord 알림용 **별도 채널** + 웹훅 생성
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
- [ ] **D9** SNS → **Discord 별도 채널** 연동, 테스트 알람 1회 발화
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
