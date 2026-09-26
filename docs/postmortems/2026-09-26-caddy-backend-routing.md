# 운영 도메인에서 로그인·관리자 페이지 접근 불가

> 작성: 2026-09-26 · 🟦 하연
> 관련: [aws-infra-design.md](../aws-infra-design.md) · PR #14(도입) → #16(수정)

## 장애 개요

- **발생 일시**: 2026-09-24 첫 배포 시점부터 (도입 시점에 이미 내재)
- **감지 방법**: 수동 발견 — 관리자 페이지 접속 시도 중 민지가 발견.
  Discord 알림·모니터링 미구축 상태(§8은 D9~D10 예정)라 자동 감지 수단 없음
- **영향 범위**: **운영 환경 전체 사용자** — 로그인·회원가입·수강이력·시간표 업로드·관리자 페이지 전부.
  사실상 **인증이 필요한 모든 기능**. 로컬 개발(`make dev`)은 정상
- **심각도**: **Critical** — 아무도 로그인할 수 없어 서비스가 실질적으로 동작하지 않음

> 시연 전 발견이라 실사용자 피해는 없었음. 다만 배포 직후 스캐너 트래픽은 유입 중이었음.

## 타임라인

| 시각 | 내용 |
| --- | --- |
| 09-24 | 1차 배포 완료. 컨테이너 5개 healthy, HTTPS 정상. **홈 화면만 확인하고 배포 성공으로 판단** |
| 09-26 | 민지가 관리자 페이지 접속 실패 보고 — "관리자 페이지 켜면 납치당함" |
| 09-26 | `openapi.json` 에 `/auth/login` 은 있는데 `POST https://<도메인>/auth/login` 이 `/login?redirect=/auth/login` 로 307 되는 것 확인 |
| 09-26 | 백엔드 라우터 prefix 전수 조사 → Caddyfile 에 `/auth` `/history` `/upload` **누락** 확인 |
| 09-26 | `/backend/*` 단일 prefix 방식으로 Caddyfile 재작성 (커밋 `56189a6`) |
| 09-26 | 프론트 이미지 재빌드(`NEXT_PUBLIC_API_URL=.../backend`) → ECR push |
| 09-26 | EC2 에 Caddyfile 전송, `.env` 의 `BACKEND_URL` 갱신, `dcp up -d --force-recreate caddy` |
| 09-26 | 로그인·관리자 페이지 정상 확인. 복구 완료 |

## 근본 원인

**Caddyfile 에서 백엔드 경로를 하나씩 나열하는 방식을 택했고, 그 목록이 불완전했다.**

도입 당시 작성한 라우팅:

```caddyfile
handle /api/* { reverse_proxy backend:8000 }
handle /admin/* { reverse_proxy backend:8000 }
handle /static/* { reverse_proxy backend:8000 }
handle /docs* { reverse_proxy backend:8000 }
handle { reverse_proxy frontend:3000 }   # 나머지
```

그런데 `app/main.py` 가 등록하는 라우터의 prefix 는 5종류가 아니라 **7종류**였다:

| prefix | Caddyfile | 결과 |
| --- | --- | --- |
| `/api/v1/*` | ✅ | 정상 |
| `/static/*` | ✅ | 정상 |
| **`/auth/*`** | ❌ **누락** | 로그인·회원가입 전부 실패 |
| **`/history/*`** | ❌ **누락** | 수강이력 조회·수정 실패 |
| **`/upload/*`** | ❌ **누락** | 시간표 이미지 업로드 실패 |
| `/admin/*` | ⚠️ 있으나 **잘못됨** | 백엔드로만 가서 프론트 관리자 **페이지**가 안 열림 |

### 두 가지 층위의 실수

**① 목록 누락** — `app/api/*.py` 의 `APIRouter(prefix=...)` 를 전수 확인하지 않고 눈에 띄는 것만 적었다.

**② `/admin` 경로 충돌** — 이쪽이 더 근본적이다.
`/admin` 은 **백엔드 API**(`app/api/admin.py`)와 **프론트 페이지**(`frontend/src/app/admin/`)가 같은 경로를 쓴다.
경로 문자열만으로는 구분이 불가능하므로, 나열 방식으로는 애초에 해결할 수 없는 문제였다.

### 왜 배포 직후 못 잡았나

배포 검증을 `curl https://<도메인>` (홈 화면)과 컨테이너 health 로만 했다.
홈은 프론트가 서빙하므로 **200 이 나왔고**, 백엔드 라우팅 문제는 드러나지 않았다.
인증이 필요한 경로를 하나도 확인하지 않았다.

## 즉시 조치

**나열 대신 전용 prefix 하나로 통합**했다. 경로 목록을 관리하지 않으므로 누락이 구조적으로 불가능해진다.

```caddyfile
handle /backend/metrics* { respond 404 }        # 메트릭 외부 비공개
handle_path /backend/* { reverse_proxy backend:8000 }   # prefix 제거 후 전달
handle /static/* { reverse_proxy backend:8000 }         # 게시글 본문의 절대경로 때문에 유지
handle { reverse_proxy frontend:3000 }
```

`handle_path` 는 `handle` 과 달리 **매칭된 prefix 를 제거하고 전달**한다.
`/backend/auth/login` → 백엔드는 `/auth/login` 으로 받으므로 애플리케이션 코드 수정이 없다.

동반 변경:

| 대상 | 변경 |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://<도메인>` → `https://<도메인>/backend` — **빌드 인자라 이미지 재빌드 필요** |
| `BACKEND_URL` (EC2 `.env`) | 동일하게 `/backend` 추가 — 회원가입 승인 링크 생성에 사용 |
| `ADMIN_USERS_URL` | **변경 없음** — 프론트 페이지 주소이므로 |

> `/static/*` 만 예외로 남긴 이유: 게시글 본문에 `/static/uploads/posts/...` 절대경로가 이미 저장돼 있어,
> `/backend` 를 붙이면 기존 이미지가 깨진다.

## 재발 방지

| 항목 | 담당 | 완료 기한 |
| --- | --- | --- |
| **배포 검증에 인증 경로 포함** — 홈 200 만으로 성공 판단 금지. 최소 `/backend/docs`, `/admin`, 실제 로그인 1회 | 🟦 하연 | D16 런북 작성 시 |
| **스모크 테스트 스크립트** — `scripts/post-deploy.sh` 에 주요 경로 status code 검증 추가 | 🟦 하연 | D16 |
| **JMeter 시나리오에 로그인 추가** — 현재 `seoganpyo-smoke.jmx` 는 `GET /`, `GET /api/v1/courses` 뿐이라 이 장애를 못 잡음 | 🟩 민지 | D6 베이스라인 측정 시 |
| **라우팅 변경 시 prefix 전수 확인** — `grep 'APIRouter(' app/api/*.py` 로 대조 | 공통 | 상시 |
| **관측 스택 조기 구축** — 4xx/5xx 급증 알람이 있었다면 배포 직후 감지 가능했음 | 🟩 민지 | D9~D10 |

## 배운 것

**"컨테이너가 healthy" 와 "서비스가 동작한다" 는 다르다.**
healthcheck 는 각 컨테이너가 자기 포트에 응답하는지만 본다. 컨테이너 **사이의 라우팅**은 검증 범위 밖이다.

**경로를 열거하는 설정은 언젠가 빠뜨린다.**
새 라우터가 추가될 때마다 프록시 설정을 함께 고쳐야 하는 구조 자체가 결함이었다.
prefix 통합은 "실수하지 않도록 주의한다" 가 아니라 **실수할 수 없게 만드는** 해결이다.

**로컬에서 재현되지 않는 버그가 있다.**
로컬은 `localhost:8080`(백엔드)과 `localhost:3000`(프론트)이 분리돼 있어 프록시를 거치지 않는다.
운영은 도메인 하나로 둘을 서빙하므로 **라우팅 계층이 추가로 존재**한다. 이 차이가 장애의 배경이었다.
