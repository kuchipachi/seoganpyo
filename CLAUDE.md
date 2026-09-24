# 서간표 (Seoganpyo) - CLAUDE.md

학생 시간표 담기 및 강의 추천 기능을 제공하는 웹 서비스 풀스택 프로젝트.

## 프로젝트 개요

- **서비스명**: 서간표
- **목적**: 학생이 수강 이력을 기반으로 시간표를 구성하고, 맞춤 강의를 추천받는 웹 서비스
- **팀원**: Minji, Hyeongwoo, Yuhwan, Hayeon
- **백엔드 스택**: FastAPI + SQLAlchemy + PostgreSQL + Redis
- **프론트엔드 스택**: Next.js + React + TypeScript
- **AI**:
  - Ollama (`exaone3.5:7.8b`) — 교수 연구 요약 · 강의계획서 PDF 요약 (Groq 는 2026-04 제거)
  - Gemini (`gemini-2.5-flash`) — 관리자 챗 / 보안 분석
- **OCR**: Mistral Pixtral (`pixtral-12b-2409`) — 시간표 이미지 OCR (외부 API)
- **모니터링 스택**: Prometheus + Grafana + Loki + Promtail

## 디렉토리 구조

```
Opensource_Project/
├── app/                          # FastAPI 백엔드
│   ├── main.py                   # FastAPI 앱 진입점, 라우터 등록, /metrics 노출
│   ├── database.py               # DB 연결 설정 (PostgreSQL + SQLAlchemy)
│   ├── dependencies.py           # 공통 의존성 (get_current_student_id - JWT 검증)
│   ├── api/                      # API 라우터
│   │   ├── auth.py               # 이메일 인증 / 회원가입 / 로그인
│   │   ├── courses.py            # 강의 목록 조회 / 검색
│   │   ├── cart.py               # 장바구니 CRUD
│   │   ├── history.py            # 수강이력 CRUD (JWT 인증 필요)
│   │   ├── users.py              # 유저 정보 조회
│   │   ├── upload.py             # 시간표 이미지 업로드 + OCR 처리
│   │   ├── syllabus.py           # 강의계획서 요약
│   │   ├── posts.py              # 커뮤니티 게시판
│   │   ├── portfolio.py          # 포트폴리오 CRUD
│   │   └── admin.py              # 관리자 전용 (크롤링, AI 요약 재생성)
│   ├── models/                   # SQLAlchemy ORM 모델
│   │   ├── user.py               # User (학생)
│   │   ├── course.py             # Course, CourseDetail
│   │   ├── professor.py          # Professor, ProfessorDetail
│   │   ├── activity.py           # Track, History, Cart
│   │   ├── post.py               # Post, Comment, PostLike
│   │   └── portfolio.py          # Portfolio
│   ├── schemas/                  # Pydantic 스키마
│   └── services/                 # 비즈니스 로직
│       ├── auth_service.py       # Redis OTP 생성/검증
│       ├── email_service.py      # SMTP 이메일 발송
│       ├── user_service.py       # 비밀번호 해싱, JWT 발급, 유저 CRUD
│       ├── history_service.py    # 수강이력 저장/조회/수정/삭제
│       ├── image_service.py      # 시간표 이미지 OCR 결과 후처리 + 과목 fuzzy 매칭
│       ├── crawl_service.py      # 교수 상세정보 크롤링 + Ollama AI 요약
│       └── syllabus_service.py   # 강의계획서 OCR + LLM 요약
├── frontend/                     # Next.js 프론트엔드
│   └── src/
│       ├── app/                  # Next.js App Router (페이지 라우팅)
│       │   ├── layout.tsx        # 루트 레이아웃 (ThemeProvider 포함)
│       │   ├── page.tsx          # 홈 페이지
│       │   ├── globals.css       # 전역 스타일 (다크모드 포함)
│       │   ├── login/            # 로그인 페이지
│       │   ├── signup/           # 회원가입 페이지
│       │   ├── course/[id]/      # 강의 상세 페이지
│       │   ├── timetable/        # 시간표 페이지
│       │   ├── profile/          # 프로필 페이지
│       │   ├── graduation/       # 졸업요건 페이지
│       │   ├── community/        # 커뮤니티 게시판
│       │   └── admin/            # 관리자 페이지
│       │       ├── monitoring/   # 서버 상태 + Grafana 대시보드 (로그/메트릭 탭)
│       │       └── professors/   # 교수 데이터 관리 (크롤링, AI 요약)
│       ├── components/           # 재사용 컴포넌트
│       │   ├── ui/               # shadcn/ui 공통 컴포넌트
│       │   ├── features/         # 기능 컴포넌트
│       │   └── layout/           # 레이아웃 (theme-provider, theme-toggle)
│       ├── hooks/                # 커스텀 훅
│       ├── lib/                  # 유틸리티
│       │   ├── api.ts            # 백엔드 API 호출 함수 모음
│       │   ├── utils.ts
│       │   └── constants/
│       └── types/
│           └── index.ts          # 공통 타입 (Course, User, Cart 등)
├── ocr-service/                  # Mistral Pixtral OCR 호출 마이크로서비스
├── infra/
│   └── observability/            # 관측 스택 설정 파일
│       ├── loki/                 # Loki 로그 저장소 설정
│       ├── promtail/             # 컨테이너 로그 수집기 설정
│       ├── prometheus/           # 메트릭 수집 설정 (backend:8000/metrics 스크랩)
│       └── grafana/
│           └── provisioning/
│               ├── datasources/  # Loki, Prometheus 데이터소스 자동 프로비저닝
│               └── dashboards/
│                   └── json/
│                       ├── seoganpyo-overview.json   # 로그 대시보드
│                       └── seoganpyo-metrics.json    # API 메트릭 대시보드
├── scripts/                      # 배포 스크립트
│   ├── pre-deploy.sh             # 배포 전 점검
│   └── post-deploy.sh            # 배포 후 헬스체크
├── tests/                        # 백엔드 테스트
├── docs/                         # 프로젝트 문서
├── Dockerfile                    # 백엔드 (prod)
├── docker-compose.yml            # 전체 서비스 (prod)
├── docker-compose.dev.yml        # 로컬 개발용 override
├── docker-compose.observability.yml  # 관측 스택 (옵트인)
└── requirements.txt
```

## 개발 규칙

### 브랜치 전략

- `main`: 배포용 브랜치
- `dev`: 통합 개발 브랜치 (기능 브랜치는 dev에 머지)
- `feat/<기능명>`: 기능 개발 브랜치
- PR은 항상 `dev` 브랜치로 보낼 것

### 커밋 컨벤션

- `feat:` - 새로운 기능 추가
- `fix:` - 버그 수정
- `refactor:` - 코드 리팩토링
- `docs:` - 문서 수정
- `chore:` - 빌드/설정 변경

### 코드 스타일

- Python: PEP8 준수, 함수/변수명 snake_case, 클래스명 PascalCase
- TypeScript: 컴포넌트명 PascalCase, 훅/유틸 camelCase
- API 엔드포인트: `/api/v1/<리소스>` 형태 권장
- 프론트엔드 API 호출은 `src/lib/api.ts`에 집중 관리

### 네이밍 룰

- 브랜치: `feat/<기능명>`, `fix/<버그명>`, `chore/<작업명>` (영문 소문자, 하이픈 구분)
- 파일명: Python `snake_case.py`, TypeScript 컴포넌트 `PascalCase.tsx`, 훅 `useCamelCase.ts`
- DB 컬럼: `snake_case`
- 환경 변수: `UPPER_SNAKE_CASE`
- Docker 컨테이너: `seoganpyo-<서비스명>` (예: `seoganpyo-api`, `seoganpyo-grafana`)

## PR 리뷰 기준

Claude가 PR을 리뷰할 때 아래 기준으로 CRITICAL / MAJOR / MINOR 분류해서 코멘트할 것.

### CRITICAL (머지 전 반드시 수정)

- `get_current_student_id` / `get_current_admin` 의존성 없이 인증 필요한 엔드포인트 노출
- 학생 A가 학생 B의 장바구니·수강이력·포트폴리오를 조회/수정 가능한 로직
- `.env` 값 (DB 비밀번호, JWT_SECRET, API 키 등) 코드에 하드코딩
- 새 SQLAlchemy 모델을 `app/main.py`에 import하지 않아 테이블이 생성되지 않는 경우
- PostgreSQL 전용 타입(`JSONB` 등) 사용으로 테스트(SQLite) 깨짐

### MAJOR (강하게 수정 권고)

- 장바구니·수강이력 중복 추가 방지 로직 누락
- 새 API 라우터를 `app/main.py`에 `include_router` 하지 않음
- 프론트엔드 API 호출을 `src/lib/api.ts` 외부에서 직접 `fetch` 처리
- TypeScript `any` 타입 사용 — `src/types/index.ts`에 타입 정의 후 교체
- Pydantic 스키마 없이 raw dict를 응답으로 반환
- 새 패키지 추가 시 `requirements.txt` 누락
- `Course.course_category` 에 `"전공"` / `"교양"` 외 값 사용 (분류 룰 위반 — 옛 `"전공필수"`/`"전공선택"`/`"일반선택"` 등 금지)
- `Professor.department` 에 `"컴퓨터공학과"` / `"교양"` 외 값 사용

### MINOR (권고)

- Python snake_case / TypeScript PascalCase·camelCase 네이밍 규칙 위반
- 불필요한 `console.log`, `print` 잔존
- API 엔드포인트가 `/api/v1/<리소스>` 형태를 따르지 않음
- 서비스 로직이 라우터에 직접 작성됨 (비즈니스 로직은 `services/`에)

## 리뷰 요청 방법

> "PR diff 확인하고 CLAUDE.md 기준으로 리뷰해줘"

## PR 생성 방법

PR 생성 요청 시 Claude는 반드시 `.github/pull_request_template.md` 양식을 채워서 작성해야 한다.
템플릿 항목을 임의로 생략하거나 순서를 바꾸지 말 것.

```
## 작업 내용
## 변경 유형
## 테스트 방법
## 체크리스트
## 페이지 변경시 화면 캡쳐
```

- **변경 유형**은 커밋 컨벤션과 동일하게 `feat / fix / refactor / chore / docs` 중 선택
- **체크리스트**는 변경 내용에 해당하는 항목만 남기고 나머지는 제거
- **화면 캡쳐**는 프론트엔드 변경이 없으면 섹션 자체를 제거
- PR 타겟 브랜치는 항상 `dev`

## 환경 변수

`.env.example`을 복사해서 `.env`로 사용:

```bash
cp .env.example .env
```

## 실행 방법

```bash
make dev      # 로컬 개발 (--reload + HMR)
make down     # 컨테이너 종료
make prod     # 배포 (pre-check → build → post-check)
make logs     # 전체 로그 스트리밍
make ps       # 컨테이너 상태 확인
make up-obs   # 관측 스택 추가 기동 (Loki + Promtail + Prometheus + Grafana)
make down-obs # 관측 스택 종료
```

## 모니터링

관측 스택은 옵트인 방식 — 평소 개발 시에는 띄우지 않아도 됨.

| 서비스     | 포트 | 역할                        |
| ---------- | ---- | --------------------------- |
| Grafana    | 3001 | 대시보드 시각화             |
| Loki       | 3100 | 로그 저장소                 |
| Prometheus | 9090 | 메트릭 저장소               |
| Promtail   | —    | 컨테이너 stdout 수집 → Loki |

- **메트릭 엔드포인트**: `GET /metrics` (prometheus-fastapi-instrumentator 자동 생성)
- **admin 모니터링 페이지**: `/admin/monitoring` — 헬스체크 + Grafana 로그/메트릭 탭 내장

## 주의사항

### 공통

- `.env` 파일은 커밋하지 않는다.
- `frontend/next-env.d.ts`는 자동 생성 파일 — `.gitignore` 처리됨, 커밋하지 않는다.

### 백엔드

- DB 테이블은 `Base.metadata.create_all()`로 자동 생성된다.
- 새 모델 추가 시 `app/main.py`의 import에 반드시 포함해야 테이블이 생성된다.
- `passlib[bcrypt]`는 bcrypt 4.x 이상과 호환되지 않아 `bcrypt==4.0.1`로 고정.
- SQLAlchemy 모델에서 PostgreSQL 전용 타입(`JSONB` 등) 사용 시 테스트(SQLite)에서 깨짐 — `from sqlalchemy import JSON` 사용.
- 새 패키지 추가 시 `requirements.txt`에 반드시 포함해야 Docker 컨테이너에 반영된다.

### AI / OCR / 크롤링

- **OCR**: `ocr-service/`는 Mistral Pixtral API(`pixtral-12b-2409`)를 호출하는 얇은 래퍼 — `MISTRAL_API_KEY` 환경변수 필요.
- **Ollama** AI 요약(교수 연구 분야·강의계획서)은 `host.docker.internal:11434`로 호스트 Ollama에 접근 — 로컬에서 별도로 `ollama serve` 실행 필요. 현재 모델: `exaone3.5:7.8b`.
- **Gemini** API(`gemini-2.5-flash`)는 관리자 챗·보안 분석에 사용 — `GEMINI_API_KEY` 필요.

### SonarCloud (코드 품질)

- **운영 방식**: SonarCloud SaaS 사용 — 서버 운영 부담 없음. PR/push 마다 GitHub Actions 가 자동 분석 → PR 페이지에 봇 코멘트로 결과 표시.
- **사유**: self-hosted SonarQube 는 VDI reset/다운으로 토큰이 자주 무효화돼 운영 비용 큼. SonarCloud 는 public 레포 무료.
- **최초 셋업** (1회):
  1. https://sonarcloud.io 가입 — GitHub 계정 연동
  2. "+" → Analyze new project → 팀 GitHub Organization 선택 → 이 리포 import
  3. 발급된 `organization key` / `projectKey` 가 `sonar-project.properties` 의 값과 일치하는지 확인 (다르면 properties 수정)
  4. Project Settings → Analysis Method 를 **"With GitHub Actions"** 로 (Automatic Analysis 끔)
  5. My Account → Security → 토큰 발급 → GitHub 팀 레포 Settings → Secrets → `SONAR_TOKEN` 으로 저장
- **분석 흐름**: PR 열거나 dev/main 에 push 하면 `.github/workflows/sonarcloud.yml` 가 자동 실행 → 약 2-5분 후 PR 에 봇 코멘트:
  ```
  ✅ Quality Gate passed
  Bugs: 0  •  Vulnerabilities: 1  •  Code Smells: 12
  Coverage: 67.3%  •  Duplications: 4.1%
  ```
- **대시보드**: https://sonarcloud.io/dashboard?id=&lt;projectKey&gt;
- **Quality Gate**: SonarCloud 의 기본 `Sonar way` 가 이미 "New Code only" 기반이라 신규 코드만 게이트. 추가 조정은 Quality Gates → Project 에 다른 게이트 적용.

### 모니터링

- `make up-obs`는 `make dev`가 실행 중인 상태에서 overlay로 추가 실행하는 것 — 단독 실행 불가.
- Docker 볼륨 마운트 전 설정 파일이 없으면 Docker가 자동으로 디렉토리를 생성해버림 → 마운트 오류 발생. `infra/observability/` 하위 설정 파일 먼저 확인.
- Grafana provisioning 파일 변경 후엔 `docker restart seoganpyo-grafana` 필요.
- Grafana 대시보드 JSON의 datasource `uid`는 provisioning YAML의 `uid`와 반드시 일치해야 함 (`loki`, `prometheus`).
- Prometheus 메트릭 라벨: `status="2xx"/"4xx"/"5xx"` (숫자 코드 아님) — 쿼리 시 `status="4xx"` 형태로 사용.
