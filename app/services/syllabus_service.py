import hashlib
import json
import os
import re

import httpx
from fastapi import HTTPException
from pypdf import PdfReader
from io import BytesIO
from sqlalchemy.orm import Session

from app.models.course import Course, CourseDetail
from app.models.professor import Professor

# Ollama 는 호스트(팀원 PC)에서 실행 — AWS 에는 없으므로 OLLAMA_TIMEOUT 을 짧게 잡아 빠르게 503 을 돌려준다.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))


def _strip_keyword_counts(keyword: str | None) -> str | None:
    """'프로젝트 3개', '과제 4번' 같은 개수 표현을 단어만 남기도록 정리."""
    if not keyword:
        return keyword
    cleaned = re.sub(r"(프로젝트|과제)\s*\d+\s*(개|번|회|차|개의)?", r"\1", keyword)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,·")
    return cleaned or None

SYSTEM_PROMPT = """당신은 대학 강의 계획서를 분석하는 전문가입니다.
모든 텍스트 필드(overview, goals, evaluation_method, teaching_method, keyword)는 강의계획서가 영어로 작성되어 있더라도 반드시 한국어로 작성하세요. 단, 프로그래밍 언어·기술 용어 등 전문 용어는 영어 그대로 사용해도 됩니다.
입력 텍스트에 한자·일본어·힌디어·그리스 문자 등이 섞여 있으면 PDF 인코딩 오류입니다. 해당 문자는 무시하고, 주변 문맥을 바탕으로 자연스러운 한국어 문장으로 직접 작성하세요. 오류 문자를 그대로 포함하거나 단순 제거하지 말고, 처음부터 올바른 한국어로 표현하세요.
반환하는 JSON의 모든 문자열 값은 한국어와 영어(전문용어)만 사용하세요.

[중요] overview와 goals는 절대로 키워드 나열로 작성하지 마세요. 반드시 완전한 문장(주어+동사+목적어가 있는 형태)으로 작성하세요.
- 나쁜 예 (키워드 나열, 절대 사용 금지): "C언어 입문, 메모리·포인터·디버깅 학습"
- 좋은 예 (완전한 문장): "C 프로그래밍 언어를 처음 배우는 학생을 위한 입문 과정입니다. 메모리 관리, 포인터, 디버깅 등 핵심 개념을 다루며 매주 실습으로 실력을 다집니다."

아래 텍스트에서 다음 항목을 추출하여 JSON으로 반환하세요.
JSON만 반환하고 다른 텍스트나 마크다운 코드블록은 포함하지 마세요.
{
  "course_code": "강의 코드. 반드시 CSE로 시작하는 7자리 코드(예: CSE2001)만 추출. 분반번호(-01 등), 괄호, AIE 코드 등 나머지는 모두 무시. 없으면 null",
  "year": 2026,
  "semester": 1,
  "overview": "강의 개요. 반드시 2-3개의 완전한 문장. 키워드 나열 절대 금지. 길이 100자 이상. 예: '컴퓨터 프로그래밍 I은 C 언어의 기초 문법과 메모리 모델을 배우는 입문 과정입니다. 매주 실습 과제를 통해 포인터·구조체·동적 메모리 할당을 직접 다루며, 학기 말 미니 프로젝트로 마무리합니다.' (없으면 null)",
  "goals": "강의 목표. 반드시 1-2개의 완전한 문장. 키워드 나열 금지. 예: 'C 언어로 자료구조를 직접 구현하고 디버깅 도구를 활용해 문제를 해결할 수 있다.' (없으면 null)",
  "evaluation_method": "평가 방식 요약 (예: 중간고사 30% 기말고사 40% 과제 20% 출석 10%, 없으면 null)",
  "teaching_method": "수업 방식 비율. 0%인 항목은 제외하고, 비율이 있는 항목만 한국어로 간결하게 작성 (예: 강의80 토론20, 강의50 실습50). 영어 표기는 한국어로 변환. '입니다' 등 불필요한 문장 종결어 제외. 없으면 null",
  "track_id": 3,
  "keyword": "기타 특징. '프로젝트'와 '과제'는 개수를 적지 말고 단어만 그대로 사용. (예: 프로젝트 과제, 발표). 없으면 null",
  "professor_name": "담당 교수 이름. 영어로 표기된 경우 한국어 성명으로 변환 (예: Youngmin Yi → 이영민). 없으면 null",
  "recommendation": "이 강의를 추천할 학생을 한 문장으로 작성. 형식 고정: '이 강의는 [구체적 학습 주제 1~2개]에 관심있는 학생에게 추천합니다.' [필수 규칙] (1) 강의계획서 본문에 등장한 구체적 기술/이론/도구/응용분야 1~2개를 골라 인용할 것 (예: 운영체제 커널, 컴파일러 최적화, 의료 영상, 분산 트랜잭션, React 상태 관리, 강화학습, 모바일 보안, 컴퓨터 비전, SQL 튜닝, 게임 엔진, 임베디드 펌웨어, LiDAR 데이터 처리, LLVM IR 변환 등). (2) '백엔드' '프론트엔드' 'AI' '데이터분석' 같은 14개 트랙명 그 자체만 단독으로 쓰지 말 것. 트랙명을 쓸 때는 반드시 구체적 주제와 함께 쓸 것. (3) 강의명·과제·평가 항목·교재에 나온 키워드를 우선 활용. [좋은 예] '이 강의는 컴파일러 프론트엔드와 LLVM IR 변환에 관심있는 학생에게 추천합니다.' / '이 강의는 자율주행 인지 시스템과 LiDAR 데이터 처리에 관심있는 학생에게 추천합니다.' [나쁜 예 - 너무 추상적] '이 강의는 AI에 관심있는 학생에게 추천합니다.' [나쁜 예 - 트랙명 단독] '이 강의는 백엔드에 관심있는 학생에게 추천합니다.' 키워드 나열 금지, 반드시 완전한 한 문장. 강의계획서에서 구체적 주제를 못 찾으면 null."
}
year는 정수, semester는 1 또는 2 정수로만 반환하세요.
track_id는 아래 목록에서 강의 내용과 가장 관련 있는 직무 1개를 정수로 반환하세요.
1:데이터분석, 2:데이터관리, 3:백엔드, 4:프론트엔드, 5:웹/앱,
6:AI, 7:DevOps, 8:네트워크, 9:보안, 10:QA,
11:게임, 12:임베디드, 13:IT컨설팅, 14:컴퓨터교육
관련 트랙을 모르겠으면 null로 반환하세요."""


def extract_pdf_text(file_bytes: bytes) -> str:
    import logging
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"AI 응답을 파싱할 수 없습니다: {raw[:200]}")


def summarize_with_ollama(text: str) -> dict:
    """
    Ollama 로컬 LLM(exaone3.5:7.8b)으로 강의계획서 텍스트 요약.
    호스트의 Ollama 서버(OLLAMA_URL)가 떠 있어야 함.
    연결 실패·시간 초과 → 503(요약 준비 중), Ollama 가 에러 응답 → 502.
    JSON 형식 출력은 Ollama의 format="json" 옵션으로 강제.

    중요: Ollama 기본 num_ctx=4096은 SYSTEM_PROMPT(~1000자) + PDF(8000자)에 부족.
    16384로 늘려야 PDF 전체가 들어가고 요약 품질이 보장됨.
    """
    prompt = f"{SYSTEM_PROMPT}\n\n강의계획서:\n\n{text[:8000]}"
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            res = client.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"num_ctx": 16384},
            })
            res.raise_for_status()
            raw = res.json().get("response", "").strip()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise HTTPException(status_code=503, detail={
            "code": "SUMMARY_UNAVAILABLE",
            "title": "요약 준비 중입니다",
            "message": "강의계획서 요약 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        }) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama 호출 실패: {e}")
    return _parse_json_response(raw)


def process_syllabus(db: Session, file_bytes: bytes) -> tuple:
    """
    Returns: (CourseDetail, course, cached: bool)
    """
    pdf_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = db.query(CourseDetail).filter(CourseDetail.pdf_hash == pdf_hash).first()
    if existing:
        course = db.query(Course).filter(Course.course_id == existing.course_id).first()
        return existing, course, True

    raw_text = extract_pdf_text(file_bytes)
    if not raw_text:
        raise HTTPException(status_code=400, detail="PDF에서 텍스트를 추출할 수 없습니다")

    result = summarize_with_ollama(raw_text)

    course_code = result.get("course_code")
    year = result.get("year")
    semester = result.get("semester")

    if not course_code or not year or not semester:
        raise HTTPException(status_code=422, detail="강의 코드 또는 학기 정보를 찾을 수 없습니다")

    course = (
        db.query(Course)
        .filter(
            Course.course_code == course_code,
            Course.year == year,
            Course.semester == semester,
        )
        .first()
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail=f"강의를 찾을 수 없습니다 (course_code={course_code}, year={year}, semester={semester})"
        )

    detail = db.query(CourseDetail).filter(CourseDetail.course_id == course.course_id).first()
    if detail is None:
        detail = CourseDetail(course_id=course.course_id)
        db.add(detail)

    detail.overview = result.get("overview")
    detail.required_skills = result.get("goals")
    detail.evaluation_method = result.get("evaluation_method")
    detail.teaching_method = result.get("teaching_method")
    detail.track_id = result.get("track_id")
    detail.keyword = _strip_keyword_counts(result.get("keyword"))
    detail.pdf_hash = pdf_hash
    detail.recommendation = result.get("recommendation")

    db.commit()
    db.refresh(detail)

    return detail, course, False


def save_course_detail(db: Session, course_id: int, result: dict, pdf_hash: str) -> CourseDetail:
    """AI 요약 결과(summarize_with_ollama 반환값)를 course_details 에 upsert. commit 은 호출자가."""
    detail = db.query(CourseDetail).filter(CourseDetail.course_id == course_id).first()
    if detail is None:
        detail = CourseDetail(course_id=course_id)
        db.add(detail)
    detail.overview = result.get("overview")
    detail.required_skills = result.get("goals")
    detail.evaluation_method = result.get("evaluation_method")
    detail.teaching_method = result.get("teaching_method")
    detail.track_id = result.get("track_id")
    detail.keyword = _strip_keyword_counts(result.get("keyword"))
    detail.pdf_hash = pdf_hash
    detail.recommendation = result.get("recommendation")
    return detail


def process_pdf_for_batch(
    db: Session,
    pdf_bytes: bytes,
    filename: str,
    year: int,
    semester: int,
    force: bool = False,
) -> dict:
    """
    배치/관리자용 PDF 처리.

    process_syllabus(단건 업로드용)와 달리:
    - HTTPException 안 던짐 → 결과를 dict로 반환 (배치 루프에서 한 PDF 실패가 전체를 막지 않음)
    - 교수명 fuzzy 매칭으로 정확한 분반 식별 (rapidfuzz)
    - 파일명 기반 fallback (예: 2026-1학기__CSE2003_01.pdf → CSE2003)
    - force=True 시 hash 캐시 우회 (단건 강제 재요약용)

    Returns:
        {
            "status": "ok" | "skip" | "warn" | "error",
            "course_ids": [int, ...],   # 저장된 course_id 목록 (skip이면 기존 course_id)
            "message": str,             # 사람이 읽을 수 있는 사유/세부 정보
        }
    """
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # 캐시 확인 (force=True 시 우회)
    if not force:
        existing = db.query(CourseDetail).filter(CourseDetail.pdf_hash == pdf_hash).first()
        if existing:
            return {"status": "skip", "course_ids": [existing.course_id], "message": "이미 처리됨"}

    # PDF 텍스트 추출
    raw_text = extract_pdf_text(pdf_bytes)
    if not raw_text.strip():
        return {"status": "error", "course_ids": [], "message": "PDF에서 텍스트를 추출할 수 없습니다"}

    # Ollama 요약
    try:
        result = summarize_with_ollama(raw_text)
    except Exception as e:
        return {"status": "error", "course_ids": [], "message": f"Ollama 오류 - {e}"}

    professor_name = result.get("professor_name")
    courses_to_save: list[Course] = []
    fuzzy_info = ""

    # 1차 매칭: 파일명에서 course_code + section 번호 추출 (가장 신뢰할 수 있는 신호)
    # 예: 2026-1학기__CSE2003_03.pdf → CSE2003 + section 3
    # AI가 영어 교수명을 잘못 한글 변환하는 경우(예: Joo Ho Lee → 이영민)에 대한 방어
    filename_match = re.match(r'^.*?__([A-Z]+\d+)_(\d+)\.pdf$', filename)
    if filename_match:
        filename_code = filename_match.group(1)
        section_num = int(filename_match.group(2))
        sections = (
            db.query(Course)
            .filter(
                Course.course_code == filename_code,
                Course.year == year,
                Course.semester == semester,
            )
            .order_by(Course.course_id)
            .all()
        )
        if 1 <= section_num <= len(sections):
            courses_to_save = [sections[section_num - 1]]

    # 2차 매칭: 파일명 매칭 실패 시 AI 추출 결과로 (교수명 fuzzy 등)
    raw_code = result.get("course_code")
    if not courses_to_save and not raw_code:
        return {"status": "error", "course_ids": [], "message": "강의 코드를 추출할 수 없습니다"}

    # AI 응답에서 CSE로 시작하는 코드만 추출 (AIE 제외)
    all_codes = re.findall(r'\bCSE[A-Z]?\d+\b', raw_code or "")
    pure_cse = [c for c in all_codes if re.match(r'^CSE\d+$', c)]
    other_cse = [c for c in all_codes if not re.match(r'^CSE\d+$', c)]
    candidates = pure_cse + other_cse if not courses_to_save else []

    for code in candidates:
        base_query = (
            db.query(Course)
            .filter(
                Course.course_code == code,
                Course.year == year,
                Course.semester == semester,
            )
        )

        # 교수 이름으로 정확한 분반 매칭
        if professor_name:
            from rapidfuzz import fuzz
            pdf_name_clean = professor_name.replace("교수님", "").replace("교수", "").strip()
            pdf_name_no_space = "".join(pdf_name_clean.split())
            # PDF 인코딩 오류로 섞인 한글/영문 외 문자(그리스어 등) 제거
            pdf_name_no_space = re.sub(
                r'[^가-힣ᄀ-ᇿ㄰-㆏a-zA-Z]',
                '',
                pdf_name_no_space,
            )
            all_sections = (
                base_query
                .join(Professor, Course.professor_id == Professor.professor_id)
                .all()
            )
            # 1차: 완전 일치
            matched = [
                c for c in all_sections
                if "".join((c.professor.name or "").split()) == pdf_name_no_space
            ]
            if matched:
                courses_to_save = matched
                break
            # 2차: 퍼지 매칭 (PDF 인코딩 오류로 이름이 일부 깨진 경우 대응)
            if all_sections:
                best = max(
                    all_sections,
                    key=lambda c: fuzz.ratio(
                        pdf_name_no_space, "".join((c.professor.name or "").split())
                    ),
                )
                best_score = fuzz.ratio(
                    pdf_name_no_space, "".join((best.professor.name or "").split())
                )
                if best_score >= 60:
                    fuzzy_info = (
                        f"퍼지 매칭: '{pdf_name_no_space}' → '{best.professor.name}' "
                        f"(유사도 {best_score:.0f}%)"
                    )
                    courses_to_save = [best]
                    break

        # 교수 이름 매칭 실패 시
        if not courses_to_save:
            all_sections = base_query.all()
            if len(all_sections) == 1:
                courses_to_save = all_sections
                break
            elif len(all_sections) > 1:
                professor_ids = {s.professor_id for s in all_sections}
                if len(professor_ids) == 1:
                    # 모든 분반 교수가 동일 → 전체 저장
                    courses_to_save = all_sections
                    break
                # 매칭 실패 → 다음 단계(파일명 section 인덱스 fallback)로 위임

    # AI 추출 실패 또는 교수명 매칭 실패 시 파일명에서 추출
    # 1차: 파일명 section 번호로 분반 인덱스 매칭 (예: _03.pdf → 3번째 분반)
    # 2차: course_code만 매칭 (인덱스 추정 불가능 시 모든 분반 일괄)
    if not courses_to_save:
        filename_match = re.match(r'^.*?__([A-Z]+\d+)_(\d+)\.pdf$', filename)
        if filename_match:
            filename_code = filename_match.group(1)
            section_num = int(filename_match.group(2))  # 1-indexed
            sections = (
                db.query(Course)
                .filter(
                    Course.course_code == filename_code,
                    Course.year == year,
                    Course.semester == semester,
                )
                .order_by(Course.course_id)
                .all()
            )
            if 1 <= section_num <= len(sections):
                # section 번호 기반 인덱스 매칭 (course_id 정렬 순서 가정)
                courses_to_save = [sections[section_num - 1]]
            elif sections:
                # 인덱스 매칭 불가 → 코드만 매칭된 모든 분반에 일괄 저장
                courses_to_save = sections

    if not courses_to_save:
        return {
            "status": "error",
            "course_ids": [],
            "message": (
                f"강의 없음 (course_code={raw_code}, year={year}, semester={semester})"
            ),
        }

    # course_details upsert — 매칭된 모든 분반에 저장
    saved_ids: list[int] = []
    for course in courses_to_save:
        save_course_detail(db, course.course_id, result, pdf_hash)
        saved_ids.append(course.course_id)

    db.commit()
    return {"status": "ok", "course_ids": saved_ids, "message": fuzzy_info}
