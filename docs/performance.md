# 성능 측정 기록

> 🟩 민지 — [cloud-migration-plan.md](./cloud-migration-plan.md) §2.8
> 개선을 수치로 남기는 문서입니다. 런북·포스트모템과는 별도로 둡니다.

## 1. Docker 이미지 최적화 (D3, 2026-09-24)

### 측정 환경

| 항목 | 값 |
| --- | --- |
| 빌드 머신 | MacBook Pro (Apple M1 Pro) — Docker Desktop 29.7.2, buildx v0.36.1 |
| 타깃 플랫폼 | `linux/amd64` (EC2 t3.micro 기준 — Apple Silicon 에서 에뮬레이션 빌드) |
| 빌드 옵션 | `docker buildx build --no-cache --platform linux/amd64 --load` |
| 공정성 조건 | 베이스 이미지는 미리 받아 둔 상태(pull 시간 제외), 매 빌드 전 BuildKit 컨텍스트 캐시 삭제(`buildx prune --filter type=source.local`) |
| 크기 기준 | `docker image inspect` 의 로컬(비압축) 크기. ECR 에 올라가는 압축 크기는 이보다 작음 |

### 결과

| 이미지 | 크기 before | 크기 after | 변화 | 빌드 시간 before → after |
| --- | --- | --- | --- | --- |
| **api** (backend) | 121.5 MB | **102.3 MB** | **−19.2 MB (−15.8%)** | 52s → **36s (−31%)** |
| ocr | 67.4 MB | 67.4 MB | 변경 없음 | 20s |
| frontend | 64.5 MB | 64.5 MB | 변경 없음 | 67s |
| **합계** | **253.4 MB** | **234.2 MB** | **−19.2 MB (−7.6%)** | |

### 무엇을 바꿨나

| 변경 | 효과 |
| --- | --- |
| backend `Dockerfile` 의 docker-cli 스테이지 삭제 | 이미지 −19.2 MB, 빌드 −16s. prod 는 docker.sock 을 마운트하지 않아 원래 쓸 수 없던 바이너리 (챗 도구는 #10 에서 자동 제외) |
| `frontend/.dockerignore` 커밋 (`.gitignore` 가 `.dockerignore` 를 무시하고 있어 레포에 없었음) | **빌드 실패 방지** — 아래 참고 |
| 루트 `.dockerignore` 신규 (허용 목록 방식) | `.env`·`*.pem` 등 비밀값이 빌드 컨텍스트에 섞이는 것 차단 |

### frontend — `.dockerignore` 가 없을 때 (재현)

`frontend/Dockerfile` 은 `COPY . .` 를 씁니다. `.dockerignore` 가 없는 개발 PC(예: 레포를 새로 받아 `pnpm install` 한 팀원)에서 빌드하면:

| | `.dockerignore` 없음 | 있음 |
| --- | --- | --- |
| 전송 컨텍스트 | **498.67 MB** (호스트 `node_modules` 포함) | 2.61 MB |
| 결과 | ❌ **빌드 실패** — `cannot copy to non-directory: .../node_modules/@radix-ui/react-accordion` | ✅ 성공 |

호스트(macOS)의 `node_modules` 가 deps 단계에서 설치한 Linux `node_modules` 위로 복사되며 충돌합니다. 기존에는 민지 로컬에만 `.dockerignore` 가 있어 드러나지 않았습니다.

### 측정하면서 알게 된 것

- **첫 측정은 불공정했다** — 처음 잰 before 값에는 베이스 이미지 pull 시간이 섞여 있었다(변경이 없는 ocr 이 44s → 19s 로 "빨라짐"). 베이스를 캐시한 뒤 다시 쟀다.
- **컨텍스트 전송량은 캐시 영향을 받는다** — BuildKit 은 같은 빌더에서 이전 컨텍스트와의 차이만 보낸다. 캐시를 지우지 않으면 6 kB 처럼 비현실적으로 작게 찍힌다.
- **루트 `.dockerignore` 의 크기 효과는 작다** (api 컨텍스트 14.57 MB → 13.47 MB) — BuildKit 이 `COPY` 대상 경로만 골라 전송하기 때문. 이 파일의 가치는 크기보다 **비밀값 차단**이다.

---

## 2. 부하 테스트 — 측정 방법 (결과를 보기 전에 확정, 2026-09-27)

> 튜닝 전후를 **믿을 수 있게** 비교하려고, 결과를 보기 전에 방법·기준·분석 규칙을 먼저 고정한다.
> 근거는 k6 문서, Google SRE Book, Brendan Gregg(USE method, 벤치마킹 체크리스트), Gil Tene(coordinated omission),
> Georges et al.(반복·신뢰구간), 컬리·우아한형제들·LINE 성능 테스트 사례. 출처는 §2.9.

### 2.1 무엇을 알고 싶은가 (가설)

1GiB EC2 에서 컨테이너 메모리 한도 합계(1,536MB)가 물리 메모리(913MB)보다 크다.
→ 부하가 오르면 OOM 이전에 **swap 스래싱으로 지연이 급격히 나빠질 것**이다.
→ 메모리 한도·swap·DB 풀·워커 수를 **한 번에 하나씩** 조정해 이 지점을 뒤로 밀 수 있는지 확인한다.

### 2.2 도구와 부하 모델

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| 도구 | **k6** (v2.3, Apple Silicon 네이티브) | 기존 JMeter 이미지는 amd64 전용 → M1 에서 에뮬레이션 + JVM 5GB. 생성기가 병목이 될 위험 |
| 부하 모델 | **open model** (`arrival-rate`: 초당 도착 수 고정) | closed model(동시 사용자 고정)은 서버가 느려지면 요청도 줄어 꼬리 지연을 과소 측정(coordinated omission) |
| 생성기 병목 판정 | `dropped_iterations == 0`, 목표 RPS ≈ 달성 RPS, Mac load average 기록 | 못 보낸 요청이 숨지 않고 지표로 남음 |
| JMeter | 교차 검증용으로 유지 | 같은 부하에서 두 도구 p95 가 비슷하면 측정 도구 신뢰 근거 |

### 2.3 시나리오 (조회 위주, 1 iteration = 사용자 행동 1회)

| 행동 | 비율 | 요청 |
| --- | --- | --- |
| 홈 화면 | 20% | `GET /` (Next.js, ~9KB) |
| 강의 목록 | 30% | `GET /backend/api/v1/courses?year=2026&semester=1` (~30KB) |
| 강의 검색 | 20% | `GET .../courses?q=<무작위 검색어 13개 중>` |
| 강의 상세 | 20% | `GET .../courses/{무작위 1~37}` + `GET .../syllabus/{id}` |
| 교수 목록 | 10% | `GET .../professors` |

- **제외**: 로그인 필요 흐름(2차에 테스트 계정으로 추가), OCR·강의계획서 요약·관리자 챗(외부 유료 API·호스트 Ollama 의존)
- 정적 자원(JS/CSS 청크)은 제외 — 브라우저 캐시 대상이라 서버 용량과 무관. **한계로 명시**
- 스크립트: `infra/loadtest/k6/seoganpyo.js`

### 2.4 테스트 종류와 합격 기준 (SLO)

| ID | 종류 | 부하 (iteration/초) | 시간 | 목적 |
| --- | --- | --- | --- | --- |
| smoke | 스모크 | 1 | 1분 | 스크립트·환경 검증 (측정 세션마다 1회) |
| **load** | 평상시 부하 | 0→5 램프 1분 + 5 유지 10분 | 11분 | **튜닝 전후 비교의 주 지표** |
| stress | 단계 증가 | 5→10→20→30→40, 단계당 3분 | 15분 | 단계별 p95·자원 변화, 급격히 나빠지는 지점 |
| breakpoint | 한계 탐색 | 1→150 선형 | 최대 20분 + 회복 관찰 5분 | SLO 만족 최대 처리량, swap 포화·OOM 지점, 회복 여부 |

| 대상 | p95 | p99 | 에러율 |
| --- | --- | --- | --- |
| API | < 500ms | < 1,500ms | < 1% |
| 페이지 | < 1,000ms | — | < 1% |

- 기준 500ms = Apdex T (JMeter 대시보드 기본값과 동일)
- **안전장치**: breakpoint 는 에러율 10% 초과가 30초 이어지면 자동 중단 (운영 서버 보호)

### 2.5 서버 쪽 동시 관찰 (USE method)

부하가 도는 **동안** EC2 에서 `scripts/loadtest/collect-server-metrics.sh` 로 수집한다 — "왜 거기서 한계인가"에 답하기 위해.

| 자원 | 도구 | 보는 것 |
| --- | --- | --- |
| CPU | `vmstat 1` | us·sy·**st**(steal), run queue(r) |
| 메모리 | `vmstat 1` | free, **si/so(swap in/out)** |
| 디스크(swap) | `iostat -xz 1` | %util, 대기열 |
| 네트워크 | `sar -n DEV 1` | 처리량 |
| 컨테이너 | `docker stats`(5초), `docker events` | 컨테이너별 메모리, **OOM·재시작** |
| 커널 | `dmesg -w` | OOM killer |
| DB | `pg_stat_activity`(5초) | state 별 연결 수 (RDS 한도 79, 앱 풀 5+10) |
| 설정 증명 | `docker inspect` (전·후) | 적용된 메모리 한도·이미지 ID·재시작 횟수 |

관측 스택(Prometheus·Loki)은 측정 대상과 1GiB 를 나눠 쓰므로 **측정 중 띄우지 않는다**.

### 2.6 신뢰도 규칙

| 규칙 | 내용 |
| --- | --- |
| 반복 | load 5회, stress 3회, breakpoint 3회 (튜닝 전·최종). 중간 튜닝 변수는 load 3회 + breakpoint 1회 |
| 워밍업 제외 | load 는 앞 120초 제외, stress 는 단계마다 앞 30초 제외 |
| percentile 계산 | Grafana 윈도우 값이 아니라 **raw 샘플**로 계산 (`scripts/loadtest/analyze.py`). percentile 끼리 평균 내지 않음 |
| 여러 회 집계 | 실행별 값의 **중앙값 [최소–최대]** |
| 전후 비교 | 실행 단위 **Mann-Whitney U**(정확 분포, 양측) + 중앙값 변화율의 **부트스트랩 95% CI** |
| 변수 통제 | 한 번에 한 설정만 변경 · 같은 시간대 · 실행 사이 5분 쿨다운 · 가능하면 before/after 교차 순서 |
| 조건 기록 | 매 실행 `conditions.txt`: git 커밋, RTT(TCP connect), EC2 CPU 크레딧, Mac load average |
| 무효 처리 | load 에서 `dropped_iterations > 0` 이면 무효 (생성기가 목표 부하를 못 냄) |

### 2.7 튜닝 변수 (한 번에 하나씩)

| 순서 | 변수 | 가설 |
| --- | --- | --- |
| V1 | 컨테이너 메모리 한도 현실화 (합계 ≤ 약 850MB, api 는 swap 금지) | 스래싱 대신 예측 가능한 성능 또는 명확한 OOM 지점 |
| V2 | 호스트 swap 크기·`vm.swappiness` | swap 진입 시점 조절 |
| V3 | DB 풀 `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` | 스레드풀(40)과 풀(15) 불일치로 인한 대기 해소 |
| V4 | uvicorn `--workers 2` | 처리량 ↑ vs 메모리·DB 연결 2배 — 트레이드오프 기록 |

### 2.8 비용·운영 영향

- 데이터 전송(EC2→집): 권장 범위 약 25GB 예상, 월 100GB 무료 한도 내 — 실행마다 누적 기록
- CPU 크레딧: T3 Unlimited — 초과분 약 $1 이내 예상 (크레딧 차감)
- 운영 서버에 부하를 거는 테스트 — **측정 시간대를 팀과 사전 공유**, breakpoint 는 자동 중단 기준 적용

### 2.9 참고

- k6 테스트 유형: https://grafana.com/docs/k6/latest/testing-guides/test-types/
- open vs closed model: https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
- coordinated omission (Gil Tene, wrk2): https://github.com/giltene/wrk2
- percentile 평균의 오류: https://bravenewgeek.com/everything-you-know-about-latency-is-wrong/
- USE method: https://www.brendangregg.com/usemethod.html · 벤치마킹 체크리스트: https://www.brendangregg.com/blog/2018-06-30/benchmarking-checklist.html
- Google SRE — SLO: https://sre.google/sre-book/service-level-objectives/ · 한계 테스트: https://sre.google/sre-book/addressing-cascading-failures/
- 반복·신뢰구간 (Georges et al.): https://www2.ccs.neu.edu/racket/Performance/andy-georges-paper.pdf
- 사례: 컬리 https://helloworld.kurly.com/blog/vsms-performance-experiment/ · 우아한형제들 https://techblog.woowahan.com/2572/ · LINE https://engineering.linecorp.com/ko/blog/server-side-test-automation-4/

### 2.10 파이프라인 검증 (smoke, 2026-09-27)

| 항목 | 결과 |
| --- | --- |
| k6 요청 | 71건, 에러 0, `dropped_iterations` 0 |
| raw 재계산 vs k6 요약 | API p95 267ms — 일치 |
| 서버 지표 | 10종 회수 (vmstat·docker stats·pg_activity·before/after 설정 등) |
| RTT (TCP connect) | 평균 약 15ms |
| CPU 크레딧 | 288 (최대치) |
| **발견** | 강의 목록 API 만 p50 236ms — 다른 API(30~50ms)의 5배. N+1 쿼리 의심 → 베이스라인 후 확인 |
