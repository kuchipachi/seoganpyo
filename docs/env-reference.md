# 환경변수 목록

> 🟩 민지 작성 → 🟦 하연 등록 (1차: EC2 `.env` / 2차: SSM Parameter Store)
> 코드에서 실제로 읽는 변수를 전수 조사한 목록입니다 (`os.getenv`, compose `${...}`, 프론트 빌드 인자).
> 기준: `dev` + PR #7(`OLLAMA_*`) — 2026-09-24

**SSM 유형**: 🔒 `SecureString`(비밀) / 📄 `String`(비밀 아님). 경로는 `/seoganpyo/prod/<KEY>`.

## 1. 필수 — 없으면 앱이 뜨지 않거나 핵심 기능이 깨짐

| 키 | SSM | 로컬 개발 | EC2 운영 | 읽는 곳 |
| --- | --- | --- | --- | --- |
| `DB_HOST` | 📄 | `host.docker.internal` (SSH 터널 경유) | RDS 엔드포인트 | `app/database.py` |
| `DB_PORT` | 📄 | `5432` | `5432` | `app/database.py` |
| `DB_NAME` | 📄 | `seoganpyo` | `seoganpyo` | `app/database.py` |
| `DB_USER` | 🔒 | RDS 사용자 | 같음 | `app/database.py` |
| `DB_PASSWORD` | 🔒 | RDS 비밀번호 | 같음 | `app/database.py` |
| `SECRET_KEY` | 🔒 | 아무 긴 문자열 | **새로 생성** (`openssl rand -hex 32`) | JWT 서명 — `user_service` |
| `ADMIN_SECRET_KEY` | 🔒 | 아무 문자열 | **새로 생성** | 관리자 API — `admin.py` |
| `SENDER_EMAIL` | 🔒 | Gmail 주소 | 같음 | 이메일 인증 — `email_service` |
| `SENDER_PASSWORD` | 🔒 | Gmail 앱 비밀번호 | 같음 | 이메일 인증 — `email_service` |
| `MISTRAL_API_KEY` | 🔒 | 발급 키 | 같음 | 시간표 OCR — `ocr-service` |
| `GEMINI_API_KEY` | 🔒 | 발급 키 | 같음 | 포트폴리오 평가·관리자 챗 — `ai_service` |

> ⚠️ `SECRET_KEY`는 운영에서 **로컬과 다른 값**을 쓰세요. 같은 값이면 로컬에서 만든 토큰이 운영에서도 통합니다.

## 2. URL — 배포 주소에 맞춰 설정

| 키 | SSM | 로컬 개발 | EC2 운영 | 비고 |
| --- | --- | --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | 📄 | `http://localhost:8080` | `https://54.180.181.46.nip.io` | ⚠️ **프론트 빌드 인자** — 런타임 `.env`가 아니라 `docker buildx build --build-arg`로 넘김. 바뀌면 재빌드 |
| `BACKEND_URL` | 📄 | `http://localhost:8080` | `https://54.180.181.46.nip.io` | 회원가입 승인 링크 |
| `ADMIN_USERS_URL` | 📄 | `http://localhost:3000/admin/users` | `https://54.180.181.46.nip.io/admin/users` | Discord 알림의 승인 링크 |

## 3. 선택 — 없어도 앱은 뜸 (해당 기능만 비활성)

| 키 | SSM | 기본값 | EC2 운영 권장 | 없을 때 |
| --- | --- | --- | --- | --- |
| `OLLAMA_URL` | 📄 | `http://host.docker.internal:11434/api/generate` | 기본값 그대로 | — |
| `OLLAMA_MODEL` | 📄 | `exaone3.5:7.8b` | 기본값 그대로 | — |
| `OLLAMA_TIMEOUT` | 📄 | `300` | **`20`** | EC2엔 Ollama가 없음 → 짧게 잡아 빠르게 503 |
| `DISCORD_SIGNUP_WEBHOOK` | 🔒 | (없음) | 가입 알림 채널 웹훅 | 가입 알림만 안 감 |
| `NEXT_PUBLIC_GRAFANA_URL` | 📄 | `http://localhost:3001` | Grafana Cloud Public dashboard URL | 관리자 모니터링 iframe — **프론트 빌드 인자** |
| `PROMETHEUS_URL` | 📄 | `http://prometheus:9090` | 1차엔 비움 → 관측 구성 후 Cloud URL | 관리자 챗 메트릭 도구 실패 (§8.1) |
| `LOG_LEVEL` | 📄 | `INFO` | `INFO` | — |
| `GEMINI_MODEL` | 📄 | `gemini-2.5-flash` | 기본값 | — |
| `GEMINI_FALLBACK_MODEL` | 📄 | `gemini-2.5-flash-lite` | 기본값 | — |
| `ADMIN_CHAT_MODEL` / `ADMIN_CHAT_FALLBACK_MODEL` | 📄 | 코드 기본값 | 기본값 | — |
| `ENABLE_SEARCH_GROUNDING` | 📄 | `true` | 기본값 | — |
| `SYLLABI_DIR` | 📄 | `data/syllabi` | 기본값 | — |
| `DEFECTDOJO_URL` / `DEFECTDOJO_TOKEN` / `DEFECTDOJO_ENGAGEMENT` | 🔒(토큰) | 비움 | **비움** (DefectDojo 범위 제외) | 관리자 보안 페이지가 503 |

## 3.5 운영 전용 — `docker-compose.prod.yml` 이 읽음

EC2 에서 ECR 이미지로 띄울 때만 필요합니다. 로컬 개발에는 불필요.

| 키 | SSM | 예시 | 비고 |
| --- | --- | --- | --- |
| `ECR_REGISTRY` | 📄 | `<계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com` | 이미지 3개의 공통 접두사 |
| `IMAGE_TAG` | 📄 | `latest` | 2차에 git SHA 로 전환 → 롤백 지점 |
| `DOMAIN` | 📄 | `54.180.181.46.nip.io` | Caddy 가 이 이름으로 인증서 발급 |

> `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` 로 실행합니다.
> base 의 `build:` 를 `image:` 로 덮어써 EC2 에서 빌드하지 않습니다 (1GiB 에서 OOM).

## 4. 설정하지 않는 것

| 키 | 이유 |
| --- | --- |
| `GROQ_API_KEY` | 코드에서 읽지 않음 — Groq는 2026-04 제거. 기존 `.env`에 있으면 지워도 됨 |
| `REDIS_URL`, `OCR_SERVICE_URL` | `docker-compose.yml`이 컨테이너 주소로 고정 주입 |
| `TEST_DATABASE_URL` | 테스트 전용 (`tests/conftest.py`가 설정) |
| `GRAFANA_USER` / `GRAFANA_PASSWORD` | 로컬 관측 스택 전용 — 운영은 Grafana Cloud |

## EC2 `.env` 최소 구성 (1차)

```bash
DB_HOST=<rds-endpoint>
DB_PORT=5432
DB_NAME=seoganpyo
DB_USER=...
DB_PASSWORD=...
SECRET_KEY=...            # 새로 생성
ADMIN_SECRET_KEY=...      # 새로 생성
SENDER_EMAIL=...
SENDER_PASSWORD=...
MISTRAL_API_KEY=...
GEMINI_API_KEY=...
BACKEND_URL=https://54.180.181.46.nip.io
ADMIN_USERS_URL=https://54.180.181.46.nip.io/admin/users
OLLAMA_TIMEOUT=20
DISCORD_SIGNUP_WEBHOOK=...   # 선택
```

`NEXT_PUBLIC_*` 두 개는 여기가 아니라 **민지가 프론트 이미지를 빌드할 때** `--build-arg`로 넣습니다.
