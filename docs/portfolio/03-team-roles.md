# 03. 팀원별 역할

> 4인 팀 / 총 179개 PR 기준 (`main`+`dev` 머지 이력)

## Minji — DB · 수강이력 · AI 요약 · MCP · 모니터링 (40 PR)

- **DB 설계·구축** — User/이력 스키마 초기 설계 (`db_design.md`, db setup)
- **수강이력 CRUD** — JWT 인증·소유권 검증·재수강 자동 산정 + 테스트
- **졸업요건 진행도** — 학번별 이수 학점 진행도 카드, 포트폴리오 초기화
- **AI 강의요약** — 강의계획서 PDF 요약 (Claude/Ollama 일원화)
- **DB MCP 서버** — postgres MCP 팀원 연결 구축
- **로그 분석 자동화** — Claude Code 로그 분석 → Discord Embed 알림
- **모니터링** — Loki·Promtail·Grafana 로그 스택 구현, Jenkins main 배포

## Hyeongwoo — OCR · 정적분석 · 운영 어시스턴트 (39 PR)

- **시간표 OCR** — 이미지 업로드 → 과목 인식 구조 설계·개선 (OCR 메인 담당)
- **이수현황 UI** — 업로드/이수현황 프론트, 계절학기·일반교양·dedup 룰
- **정적 분석** — SonarQube → SonarCloud 전환 + CI Quality Gate 통합
- **E2E 테스트** — Playwright 도입
- **운영 어시스턴트** — Gemini 기반 Prometheus/Grafana/Docker 자연어 운영
- **포트폴리오 AI 평가** — 별점 rubric, ai_service 503 폴백, React Query 캐시

## Yuhwan — 보안(DevSecOps) · 커뮤니티 · CI/CD (46 PR)

- **보안 스캔 통합** — Trivy·Snyk(SAST)·ZAP(DAST) → DefectDojo 통합 + MCP
- **취약점 대응** — 보안 헤더 미들웨어, CVE 패치, JWT PyJWT 마이그레이션
- **보안 모니터링 페이지** — 관리자 SAST/DAST 대시보드 + AI 챗봇
- **커뮤니티** — 게시판·관심분야·게시글 신고·댓글 좋아요
- **회원 관리** — 가입 승인 대기, 회원탈퇴, Discord 가입 알림
- **CI/CD** — Jenkins 파이프라인·테스트 환경, 후보 시간표 4슬롯 비교

## Hayeon — 랜딩·프론트 · 관측 인프라 · 부하 테스트 (54 PR)

- **랜딩 페이지** — 애플 스타일 single-page scroll, 다크모드 전체 적용
- **회원/API 통합** — 회원가입, API 연동, 교수 상세 페이지
- **관측 인프라** — Prometheus 메트릭, observability 스택 분리, Grafana
- **CI 보안** — CI 자동화 + MCP, 취약점 보안 테스트
- **부하 테스트** — JMeter + InfluxDB 부하 테스트 스택
- **관리자** — 교수 패널·admin DB, 미들웨어 비로그인 접근 차단

---

> 협업은 `feat/*` → `dev` → `main` 브랜치 전략, PR 리뷰 후 머지로 진행.
