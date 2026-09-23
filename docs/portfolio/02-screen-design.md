# 02. 화면설계서

## 디자인 시스템

- **프레임워크**: Next.js 16 (App Router) + Tailwind CSS v4 + shadcn/ui
- **브랜드 컬러**: 서강대 교색 Crimson `#B0232A` (강조·CTA·아이콘)
- **폰트**: Noto Sans KR(본문) / 이서윤체(로고) / Geist Mono(시간표 라벨)
- **테마**: 라이트·다크 모드 토글 (`next-themes`)

## 화면 목록 (라우팅)

| 화면 | URL | 인증 | 역할 |
|------|-----|------|------|
| 랜딩 | `/` | 공개 | 서비스 소개, 회원가입/로그인 진입 |
| 인증 | `/login`, `/signup` | 공개 | 이메일 인증 로그인·가입 |
| 대시보드 | `/dashboard` | 필수 | 관심 과목·시간표·포트폴리오 진입 허브 |
| 시간표 | `/timetable` | 필수 | **이미지 OCR 업로드** + 시간표 편집 |
| 강의 상세 | `/course/[id]` | 필수 | 강의계획서·교수 정보 |
| 교수 | `/professors/[id]` | 필수 | 연구분야 AI 요약 |
| 졸업요건 | `/graduation` | 필수 | 학점 이수 현황 시각화 |
| 포트폴리오 | `/portfolio` | 필수 | 활동 기록 + AI 진로 평가 |
| 커뮤니티 | `/community/[category]` | 필수 | 관심분야별 게시판 |
| 관리자 | `/admin/*` | 관리자 | 운영 도구·모니터링 |

> 라우팅 보호는 `middleware.ts`에서 일괄 처리, `/`만 public.

## 핵심 화면 레이아웃

### 랜딩 (`/`)
애플 스타일 single-page scroll — 6개 섹션 순차 노출, Framer Motion fade-up 애니메이션.
`Header → Hero(CTA+목업) → OCR 소개 → AI 요약 → 커뮤니티 → CTA → Footer`

### 앱 내부 (대시보드 이후)
- **Header**: 좌측 로고 / 우측 프로필·저장개수·테마토글
- **본문**: 단일 컬럼, 좌측 크림슨 액센트(`border-l-2`), 카드형 그리드
- **사이드바 없음** — 페이지 이동은 라우팅으로

## 반응형

| 구간 | 레이아웃 |
|------|---------|
| Mobile (<640px) | 단일 컬럼, 카드형 액션 |
| Tablet (640px~) | 2컬럼 그리드 |
| Desktop (1024px~) | 풀 레이아웃 |

## 공통 컴포넌트

- **Button**: Primary(크림슨 pill) / Secondary(outline) / Ghost / Destructive
- **Card**: `rounded-2xl border bg-card shadow-sm` + hover 인터랙션
- **Feedback**: Toast(Sonner) · Modal(Dialog) · Skeleton(로딩)

---

> 상세 명세: `docs/ui_design_spec.md` (컬러 토큰·타이포 hierarchy 전체)
