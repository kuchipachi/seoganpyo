# API 보안 점검 — 2026-11-01

> 🟩 민지 · 대상: 운영 API(FastAPI, `/backend/*`) · 방법: 권한 매트릭스 + Schemathesis(명세 퍼징) + 수동 점검
> 원칙: 공격성 테스트는 **로컬 재현 환경**에서만, 운영에는 관찰만. 실제 학생 데이터 미사용. 수정 배포 후 보고서 공개.

## 요약

| # | 발견 | 등급 | OWASP API | 상태 |
| --- | --- | --- | --- | --- |
| 1 | 장바구니·수강이력 레거시 경로가 **본인 확인 없이** 열림 (학번만 바꾸면 남의 데이터 조회·삭제) | **CRITICAL** | API1 BOLA | ✅ #54 |
| 2 | OTP(이메일 인증·비번 재설정) **무차별 대입 가능** (시도 제한 없음) | **MAJOR** | API2 인증 | ✅ #58 |
| 3 | CORS 가 **임의 출처를 반영** (`*` + credentials) | **MAJOR** | API8 설정 | ✅ #59 |
| 4 | 승인 화면·관리자 메일에 사용자 입력이 **이스케이프 없이** 삽입 (XSS·헤더 주입) | MAJOR | API8 / A03 | ✅ #55 |
| 5 | 강의 목록 `limit=-5` 등으로 **500** (입력 검증 누락) | MINOR | API8 | ✅ #57 |
| 6 | API 문서·명세 공개 (`/docs`, `/openapi.json`) | MINOR | 정보 노출 | 📋 아래 |
| 7 | 권한 매트릭스 전수 점검 — #54 외 **추가 구멍 없음** | — | — | ✅ #56 |

CRITICAL·MAJOR 5건은 수정·머지 완료. 재발 방지 테스트를 함께 넣어 CI 가 지킨다.

## 점검 방법

1. **권한 매트릭스** (`tests/test_authz_matrix.py`) — 전 경로(98개)를 ① 토큰 없이 ② 학생 토큰으로 `/admin/*` ③ 학생 B 토큰으로 A 의 데이터 호출. 공개 허용 21개는 이유와 함께 `PUBLIC` 에 명시, 그 외는 전부 401/403 이어야 통과.
2. **Schemathesis** — 명세의 104개 작업에 학생 토큰으로 경계·이상 입력 961케이스 퍼징. 500·명세 불일치 탐지.
3. **수동** — 인증 흐름(OTP·JWT), CORS, 보안 헤더, 메일/화면의 사용자 입력 처리.

## 발견 상세

### 1. BOLA — 레거시 장바구니·수강이력 (CRITICAL, #54)
`GET/POST/DELETE /api/v1/users/{student_id}/cart`·`.../history` 6개가 토큰의 학번이 아니라 **경로의 학번**으로 동작. 토큰 없이 `…/users/1/cart` 호출 시 200. 같은 기능의 토큰 경로(`/api/v1/cart`, `/history/me`)가 이미 있고 프론트는 그쪽만 사용 → 레거시 6개 삭제. 재발 방지: `{student_id}` 경로는 인증 의존성을 거쳐야 한다는 테스트(`tests/test_route_auth.py`).

### 2. OTP 무차별 대입 (MAJOR, #58)
6자리 OTP 검증(`verify-code`·`reset-password`)에 시도 횟수 제한이 없어, 3분 TTL 안에서 코드를 무한히 시도 가능 — 비번 재설정은 계정 탈취로 직결. 조치: 코드당 5회 초과 시 폐기(Redis 카운터, 코드와 함께 만료), 난수를 `secrets` 로, 비교를 `compare_digest` 로.

### 3. CORS 임의 출처 반영 (MAJOR, #59)
`allow_origins=["*"] + allow_credentials=True` 는 요청 Origin 을 그대로 반영. 운영은 프론트·API 동일 출처라 CORS 가 불필요 → 허용 출처를 `CORS_ALLOW_ORIGINS` 로 제한.

### 4. 저장형 XSS·헤더 주입 (MAJOR, #55)
회원가입 이름·이메일과 문의 제목·내용이 승인 완료 화면(관리자, 동일 도메인)과 관리자 메일에 이스케이프 없이 삽입. 조치: `html.escape`, 메일 제목 줄바꿈 제거.

### 5. 입력 검증 — 음수 페이지 파라미터 (MINOR, #57)
`GET /api/v1/courses?limit=-5` → Postgres `LIMIT must not be negative` 500. 조치: `limit` `ge=0,le=1000`, `offset` `ge=0` → 422.

> Schemathesis 가 보고한 500 중 나머지 6종은 **로컬 환경 탓**(재현 DB 에 Redis 없음으로 인증 흐름 500, 퍼징이 테스트 계정 삭제 후 발생한 FK 위반)으로 운영 버그가 아님을 재현해 확인.

### 6. API 문서·명세 공개 (MINOR, 미조치 — 판단 필요)
운영 `/backend/docs`·`/backend/openapi.json`·`/redoc` 가 인증 없이 열려 공격자에게 전체 엔드포인트 지도를 제공. 끄는 것도 가능하나(운영에서 `docs_url=None`), 시연·개발 편의와 트레이드오프라 팀 판단으로 남김. 끈다면 별도 PR.

## 남은 것 (후속)

- **OWASP ZAP** 능동 스캔(로컬) — 주입·XSS 자동 점검. 이번엔 수동·Schemathesis 로 대체, 정식 스캔은 후속
- 로그인·관리자 로그인 속도 제한 — OTP 와 달리 즉시 위험은 낮으나 무차별 대입 방어로 검토
- #6 문서 공개 여부 결정
- `security-scan.yml`(Trivy)·`sonarcloud.yml` 자동 트리거 재활성화 여부

## 재발 방지 (CI 가 지키는 것)

| 테스트 | 막는 것 |
| --- | --- |
| `test_authz_matrix.py` | 인증·관리자 권한·본인 확인 구멍 (새 경로 자동 포함) |
| `test_route_auth.py` | `{student_id}` 경로의 인증 누락 |
| `test_otp_bruteforce.py` | OTP 무차별 대입 |
| `test_cors.py` | CORS 임의 출처 반영 |
| `test_html_escaping.py` | 메일·화면의 미이스케이프 |
| `test_courses.py::TestCourseListParamBounds` | 페이지 파라미터 500 |
