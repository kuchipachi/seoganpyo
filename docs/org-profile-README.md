<!--
  GitHub 조직 프로필 README
  이 파일을 조직(gibunijjaejo)의 `.github` 레포에 `profile/README.md` 경로로 올리면
  조직 메인 페이지 상단에 렌더링됩니다.
-->

<div align="center">

# 📚 서간표 (Seoganpyo)

### AI 기반 학업 컨설팅 플랫폼

> 시간표 이미지 한 장만 올리면 — **졸업 요건 충족 여부 · 맞춤 강의 · 강의계획서 요약**까지 한 번에.

서강대학교 학생을 위한 풀스택 학업 보조 웹 서비스를 만드는 4인 개발 조직입니다.

[![Project](https://img.shields.io/badge/Repo-Opensource__Project-181717?style=flat-square&logo=github)](https://github.com/gibunijjaejo/Opensource_Project)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

</div>

---

## 🚀 우리가 만드는 것

**서간표**는 학생의 수강 이력과 시간표를 바탕으로 졸업 요건을 자동 계산하고, 맞춤 강의를 추천하는 학업 컨설팅 플랫폼입니다.

| 기능 | 한 줄 설명 |
|------|-----------|
| 🖼️ **시간표 OCR** | 이미지 업로드 → Mistral Pixtral 비전 LLM → 과목·연도·학기 자동 추출 + DB fuzzy 매칭 |
| 🎓 **졸업 요건 자동 계산** | 수강이력 + 학과 로드맵 비교 → 이수 학점·필수 과목 충족 여부 시각화 |
| 📄 **강의계획서 AI 요약** | PDF → Groq llama-3.3-70b → 강의 목표·평가 비중·주차별 학습 내용 구조화 |
| 🔬 **교수 연구분야 요약** | 학교 페이지 크롤링 → 로컬 Ollama exaone3.5 → 한국어 학술 요약 |
| 🛒 **강의 찜·장바구니** | JWT 기반 본인 데이터 격리 |
| 💬 **커뮤니티 / 관리자 챗봇** | 익명 게시판 + Gemini MCP tool use 기반 자연어 운영 |

---

## 🛠️ 기술 스택

**Backend** &nbsp;`FastAPI` · `SQLAlchemy 2.0` · `Pydantic 2` · `PostgreSQL 15` · `Redis 7`
**Frontend** &nbsp;`Next.js 16 (App Router)` · `React 19` · `TypeScript` · `Tailwind CSS 4` · `shadcn/ui` · `TanStack Query`
**AI / LLM** &nbsp;`Mistral Pixtral (OCR)` · `Groq llama-3.3-70b` · `Ollama exaone3.5` · `Gemini 2.5-flash`
**Infra / DevOps** &nbsp;`Docker Compose` · `Jenkins` · `SonarQube` · `Trivy` · `Snyk` · `DefectDojo` · `ZAP`
**Observability** &nbsp;`Prometheus` · `Grafana` · `Loki` · `Promtail`
**Agent** &nbsp;`Model Context Protocol (MCP)` 5종 — postgres · seoganpyo · grafana · docker · github

---

## 📦 레포지토리

| 레포 | 설명 |
|------|------|
| [**Opensource_Project**](https://github.com/gibunijjaejo/Opensource_Project) | 서간표 풀스택 모노레포 (FastAPI · Next.js · OCR 서비스 · 관측 스택) |

---

## 👥 팀

학생 4인이 백엔드·프론트엔드·AI·인프라를 나눠 함께 개발합니다.

**Minji** · **Hyeongwoo** · **Yuhwan** · **Hayeon**

---

<div align="center">

학업이 막막한 학생에게, 시간표 한 장으로 길을 보여주는 것을 목표로 합니다. 🎯

</div>
