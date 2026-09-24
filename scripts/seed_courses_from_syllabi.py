"""강의계획서 PDF 에서 강의(courses)·교수(professors)를 적재.

개설과목 엑셀이 없을 때 쓰는 대안. data/syllabi/ 의 PDF 첫 장(과목명·학점·수업시간·
수강대상·담당교수)을 정규식으로 파싱해 courses 행을 만든다. AI 요약은 하지 않는다 —
적재 후 기존 배치(scripts/summarize_syllabi.py)가 이 강의들에 요약을 붙인다.

사용법:
    PYTHONPATH=. python scripts/seed_courses_from_syllabi.py            # dry-run: 파싱 결과만 출력
    PYTHONPATH=. python scripts/seed_courses_from_syllabi.py --apply    # DB 적재
    OLLAMA_URL=http://localhost:11434/api/generate \
    PYTHONPATH=. python scripts/seed_courses_from_syllabi.py --summarize   # 적재된 강의에 AI 요약 저장

--summarize 를 쓰는 이유: 기존 배치(summarize_syllabi.py)는 "파일명 분반 번호 = N 번째 분반"
으로 강의를 추측한다. 이 시드처럼 분반이 일부만 있으면(예: CSE3013 은 _02~_05 만 존재)
엉뚱한 분반에 요약이 붙는다. 여기서는 PDF 마다 적재한 강의를 정확히 찾아 저장한다.

파일명 규칙: <YEAR>-<TERM>학기__<COURSE_CODE>_<SECTION>.pdf  (예: 2026-1학기__CSE2003_01.pdf)
  - course_code·분반은 파일명이 기준 (PDF 본문의 과목번호는 표기가 제각각이라 신뢰하지 않음)
  - 같은 과목의 분반은 분반 번호 순서로 INSERT → process_pdf_for_batch 가
    "course_id 순서 = 분반 번호" 로 매칭하므로 순서를 지켜야 함

교수 처리:
  - cs.sogang.ac.kr 교수 목록을 읽어(읽기 전용) 전임 교수 전원을 professors 에 넣는다
    (crawl_and_upsert 는 DB 에 있는 교수만 갱신하므로 먼저 만들어 둬야 함)
  - PDF 의 교수 이메일 → 학과 홈페이지 이메일로 매칭해 한글 이름 확정 (영문 표기 대응)
  - 매칭 안 되면 PDF 의 한글 이름으로 새로 만든다

중복 판정: import_courses.py 와 같은 키
  (course_code, year, semester, class_days, class_start_time, class_end_time, professor_id)
  → 여러 번 실행해도, 나중에 개설과목 엑셀을 추가 적재해도 중복되지 않는다.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pypdf import PdfReader  # noqa: E402

DEFAULT_DIR = PROJECT_ROOT / "data" / "syllabi"
FILENAME_RE = re.compile(r"^(?P<year>\d{4})-(?P<term>\d)학기__(?P<code>[A-Z0-9]+)_(?P<section>\d+)\.pdf$")

# course_details.track_id 가 참조하는 직무 트랙 — syllabus_service.SYSTEM_PROMPT 의 번호와 동일
TRACKS = {
    1: "데이터분석", 2: "데이터관리", 3: "백엔드", 4: "프론트엔드", 5: "웹/앱",
    6: "AI", 7: "DevOps", 8: "네트워크", 9: "보안", 10: "QA",
    11: "게임", 12: "임베디드", 13: "IT컨설팅", 14: "컴퓨터교육",
}

KO_DAYS = "월화수목금토일"
EN_DAY_TOKENS = [  # 긴 토큰 먼저
    ("tuesday", "화"), ("thursday", "목"), ("monday", "월"), ("wednesday", "수"), ("friday", "금"),
    ("thur", "목"), ("thu", "목"), ("thr", "목"), ("tue", "화"), ("mon", "월"), ("wed", "수"), ("fri", "금"),
]
EN_DAY_LETTERS = {"M": "월", "T": "화", "W": "수", "R": "목", "F": "금"}
GRADE_WORDS = {"freshman": 1, "sophomore": 2, "junior": 3, "senior": 4}

TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(?:AM|PM|am|pm)?\s*[~–\-]\s*(\d{1,2}):(\d{2})")
EMAIL_RE = re.compile(r"[\w.\-]+@sogang\.ac\.kr")


@dataclass
class ParsedCourse:
    filename: str
    year: int
    semester: int
    course_code: str
    section: int
    course_name: Optional[str]
    credits: int
    class_days: Optional[str]
    class_start_time: Optional[str]
    class_end_time: Optional[str]
    target_grade: Optional[str]
    professor_name: Optional[str]
    professor_email: Optional[str]


def _header_text(path: Path) -> str:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    text = PdfReader(str(path)).pages[0].extract_text() or ""
    return re.sub(r"\s+", " ", text)


def _between(text: str, starts: list[str], ends: list[str], limit: int = 120) -> Optional[str]:
    for s in starts:
        i = text.find(s)
        if i < 0:
            continue
        seg = text[i + len(s): i + len(s) + limit]
        cut = min([seg.find(e) for e in ends if seg.find(e) >= 0] or [len(seg)])
        val = seg[:cut].strip(" :：○-")
        if val:
            return val
    return None


def _parse_name(text: str) -> Optional[str]:
    name = _between(
        text,
        ["과목명", "과 목 명:", "Course Title"],
        ["학기", "과목번호", "구분", "○", "Course Number", "Semester", "Credit"],
    )
    return re.sub(r"\s+", " ", name).strip() if name else None


def _parse_credits(text: str) -> int:
    m = re.search(r"(?:학점\)?|Credit)\s*[:：]?\s*(?:이론\s*\(\s*)?(\d)(?:\.\d)?", text)
    return int(m.group(1)) if m else 3


SCHEDULE_ENDS = ["수강대상", "강의실", "담당교수", "성명", "○", "Classroom", "Enrollment", "Instructor", "Name:"]


def _schedule_segment(text: str) -> Optional[str]:
    """'수업시간' 뒤 ~ 다음 항목 이름 앞. 다음 항목(예: 수강대상)의 '수'가 요일로 잡히지 않게 자른다."""
    for label in ["수업시간", "Class Time", "Meeting Times"]:
        i = text.find(label)
        if i >= 0:
            seg = text[i + len(label): i + len(label) + 70]
            cut = min([seg.find(e) for e in SCHEDULE_ENDS if seg.find(e) >= 0] or [len(seg)])
            return seg[:cut]
    return None


def _parse_days(seg: str) -> Optional[str]:
    seg = seg.replace("요일", "")
    ko = "".join(ch for ch in seg if ch in KO_DAYS)
    if ko:
        return "".join(dict.fromkeys(ko))  # 순서 유지 중복 제거
    low = seg.lower()
    found: list[tuple[int, str]] = []
    taken = [False] * len(low)
    for token, day in EN_DAY_TOKENS:
        for m in re.finditer(token, low):
            if not any(taken[m.start():m.end()]):
                found.append((m.start(), day))
                for k in range(m.start(), m.end()):
                    taken[k] = True
    if found:
        return "".join(dict.fromkeys(d for _, d in sorted(found)))
    m = re.match(r"\s*([MTWRF]{1,3})\b", seg)  # "WF", "MW", "TR"
    if m:
        return "".join(EN_DAY_LETTERS[c] for c in m.group(1))
    return None


def _parse_times(seg: str) -> tuple[Optional[str], Optional[str]]:
    m = TIME_RE.search(seg)
    if not m:
        return None, None
    sh, sm, eh, em = (int(x) for x in m.groups())
    return f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}"


def _parse_grade(text: str) -> Optional[str]:
    seg = _between(
        text,
        ["수강대상", "Enrollment Eligibility"],
        ["담당교수", "성명", "수업시간", "강의실", "Classroom", "Class Time", "Instructor", "Name:", "○", "학번"],
        limit=60,
    )
    if not seg:
        return None
    grades: set[int] = set()
    for m in re.finditer(r"(\d)\s*[-~,/]\s*(\d)\s*학년|학년\s*(\d)\s*[-~]\s*(\d)", seg):
        lo, hi = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        grades.update(range(int(lo), int(hi) + 1))
    grades.update(int(g) for g in re.findall(r"(\d)\s*(?:학년|st|nd|rd|th)", seg))
    for word, g in GRADE_WORDS.items():
        if word in seg.lower():
            grades.add(g)
    grades = {g for g in grades if 1 <= g <= 4}
    return ",".join(str(g) for g in sorted(grades)) or None


def _clean_person(raw: str) -> Optional[str]:
    raw = re.sub(r"\(사진\)|교수님|교수|Prof\.", "", raw).strip(" :：,")
    paren_ko = re.search(r"\(([가-힣\s]{2,6})\)", raw)
    if paren_ko:
        return paren_ko.group(1).replace(" ", "")
    ko = re.match(r"^([가-힣](?:\s?[가-힣]){1,4})", raw)
    if ko:
        return ko.group(1).replace(" ", "")
    en = re.match(r"^([A-Za-z]+(?:\s[A-Za-z]+){1,2})", raw)
    return en.group(1) if en else None


def _parse_professor(text: str) -> tuple[Optional[str], Optional[str]]:
    raw = _between(
        text,
        ["성명:", "성명 :", "성명", "이름:", "Name:", "Instructor:", "담당교수:", "담당교수 :"],
        ["홈페이지", "Homepage", "과목홈페이지", "E-mail", "e-mail", "R9", ",", "연락처"],
        limit=40,
    )
    name = _clean_person(raw) if raw else None
    email = EMAIL_RE.search(text)
    return name, (email.group(0).lower() if email else None)


def parse_pdf(path: Path) -> ParsedCourse:
    filename = unicodedata.normalize("NFC", path.name)  # macOS 는 한글 파일명을 NFD 로 저장
    fm = FILENAME_RE.match(filename)
    if not fm:
        raise ValueError(f"파일명 규칙 위반: {filename}")
    text = _header_text(path)
    seg = _schedule_segment(text) or ""
    start, end = _parse_times(seg)
    prof_name, prof_email = _parse_professor(text)
    return ParsedCourse(
        filename=filename,
        year=int(fm.group("year")),
        semester=int(fm.group("term")),
        course_code=fm.group("code"),
        section=int(fm.group("section")),
        course_name=_parse_name(text),
        credits=_parse_credits(text),
        class_days=_parse_days(seg),
        class_start_time=start,
        class_end_time=end,
        target_grade=_parse_grade(text),
        professor_name=prof_name,
        professor_email=prof_email,
    )


def unify_course_names(parsed: list[ParsedCourse]) -> None:
    """같은 과목의 분반끼리 과목명을 하나로 — 한글 이름 우선 (영문 강의계획서 분반 대응)."""
    by_code: dict[str, list[ParsedCourse]] = {}
    for pc in parsed:
        by_code.setdefault(pc.course_code, []).append(pc)
    for group in by_code.values():
        names = [pc.course_name for pc in sorted(group, key=lambda c: c.section) if pc.course_name]
        korean = [n for n in names if re.search(r"[가-힣]", n)]
        chosen = (korean or names or [None])[0]
        for pc in group:
            pc.course_name = chosen


def fetch_faculty() -> list[dict]:
    """학과 홈페이지 교수 목록 + 상세(이메일). 읽기 전용."""
    from app.services.crawl_service import _parse_detail_page, _parse_list_page

    faculty = []
    for wp in _parse_list_page():
        email = None
        if wp["detail_url"]:
            try:
                email = (_parse_detail_page(wp["detail_url"]).get("email") or "").strip().lower() or None
            except Exception as e:  # 상세 페이지 하나 실패해도 계속
                print(f"  ! 상세 페이지 실패 {wp['name']}: {e}")
        faculty.append({"name": wp["name"], "email": email})
    return faculty


def resolve_professor(pc: ParsedCourse, faculty: list[dict]) -> tuple[Optional[str], str]:
    """(최종 이름, 출처) — 출처: email / name / pdf"""
    if pc.professor_email:
        for f in faculty:
            if f["email"] == pc.professor_email:
                return f["name"], "email"
    if pc.professor_name:
        for f in faculty:
            if f["name"].replace(" ", "") == pc.professor_name:
                return f["name"], "name"
    return pc.professor_name, "pdf"


def _register_models() -> None:
    """외래키(track_id → tracks 등) 해석을 위해 app/main.py 와 같은 모델 전부를 등록."""
    from app.models import user, course, professor, activity, post, report, notice  # noqa: F401
    from app.models import portfolio, contact, admin_message  # noqa: F401


def apply(parsed: list[ParsedCourse], faculty: list[dict]) -> dict:
    from app.database import Base, SessionLocal, engine
    from app.models.activity import Track
    from app.models.course import Course
    from app.models.professor import Professor

    _register_models()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    stats = {"tracks_created": 0, "professors_created": 0, "courses_inserted": 0, "courses_skipped": 0}
    try:
        existing_tracks = {t.track_id for t in db.query(Track).all()}
        for track_id, track_name in TRACKS.items():
            if track_id not in existing_tracks:
                db.add(Track(track_id=track_id, track_name=track_name))
                stats["tracks_created"] += 1
        db.flush()

        prof_index = {p.name: p.professor_id for p in db.query(Professor).all()}

        def get_or_create(name: str) -> int:
            if name not in prof_index:
                p = Professor(name=name, department="컴퓨터공학과")
                db.add(p)
                db.flush()
                prof_index[name] = p.professor_id
                stats["professors_created"] += 1
            return prof_index[name]

        for f in faculty:
            get_or_create(f["name"])

        for pc in sorted(parsed, key=lambda c: (c.year, c.semester, c.course_code, c.section)):
            name, _ = resolve_professor(pc, faculty)
            prof_id = get_or_create(name) if name else None
            exists = (
                db.query(Course.course_id)
                .filter(
                    Course.course_code == pc.course_code,
                    Course.year == pc.year,
                    Course.semester == pc.semester,
                    Course.class_days == pc.class_days,
                    Course.class_start_time == pc.class_start_time,
                    Course.class_end_time == pc.class_end_time,
                    Course.professor_id == prof_id,
                )
                .first()
            )
            if exists:
                stats["courses_skipped"] += 1
                continue
            db.add(Course(
                course_code=pc.course_code,
                course_name=pc.course_name or pc.course_code,
                credits=pc.credits,
                target_grade=pc.target_grade,
                is_english=False,
                class_days=pc.class_days,
                class_start_time=pc.class_start_time,
                class_end_time=pc.class_end_time,
                professor_id=prof_id,
                year=pc.year,
                semester=pc.semester,
                course_category="전공" if pc.course_code.startswith("CSE") else "교양",
            ))
            stats["courses_inserted"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return stats


def _find_course_id(db, pc: ParsedCourse, faculty: list[dict]) -> Optional[int]:
    from app.models.course import Course
    from app.models.professor import Professor

    name, _ = resolve_professor(pc, faculty)
    prof = db.query(Professor).filter(Professor.name == name).first() if name else None
    row = (
        db.query(Course.course_id)
        .filter(
            Course.course_code == pc.course_code,
            Course.year == pc.year,
            Course.semester == pc.semester,
            Course.class_days == pc.class_days,
            Course.class_start_time == pc.class_start_time,
            Course.class_end_time == pc.class_end_time,
            Course.professor_id == (prof.professor_id if prof else None),
        )
        .first()
    )
    return row[0] if row else None


def summarize(files: list[Path], parsed: list[ParsedCourse], faculty: list[dict], force: bool) -> dict:
    """PDF → 정확한 course_id 에 Ollama 요약 저장. PDF 하나 실패해도 계속."""
    import hashlib

    from app.database import SessionLocal
    from app.models.course import CourseDetail
    from app.services import syllabus_service

    _register_models()
    db = SessionLocal()
    stats = {"ok": 0, "skip": 0, "error": 0}
    try:
        for i, (path, pc) in enumerate(zip(files, parsed), 1):
            label = f"[{i}/{len(files)}] {pc.course_code}_{pc.section:02d}"
            course_id = _find_course_id(db, pc, faculty)
            if course_id is None:
                print(f"{label} ✗ 적재된 강의 없음 (--apply 먼저)")
                stats["error"] += 1
                continue
            pdf_bytes = path.read_bytes()
            pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
            existing = db.query(CourseDetail).filter(CourseDetail.course_id == course_id).first()
            if existing and existing.pdf_hash == pdf_hash and existing.overview and not force:
                print(f"{label} - 이미 요약됨 (course_id={course_id})")
                stats["skip"] += 1
                continue
            try:
                result = syllabus_service.summarize_with_ollama(syllabus_service.extract_pdf_text(pdf_bytes))
            except Exception as e:
                print(f"{label} ✗ Ollama 실패: {e}")
                stats["error"] += 1
                continue
            syllabus_service.save_course_detail(db, course_id, result, pdf_hash)
            db.commit()
            print(f"{label} ✓ course_id={course_id} track={result.get('track_id')}", flush=True)
            stats["ok"] += 1
    finally:
        db.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="강의계획서 PDF → courses/professors 적재")
    parser.add_argument("dir", nargs="?", default=str(DEFAULT_DIR))
    parser.add_argument("--apply", action="store_true", help="DB 에 적재 (없으면 dry-run)")
    parser.add_argument("--summarize", action="store_true", help="적재된 강의에 Ollama 요약 저장")
    parser.add_argument("--force", action="store_true", help="--summarize 시 이미 요약된 강의도 다시")
    args = parser.parse_args()

    files = sorted(Path(args.dir).glob("*.pdf"))
    if not files:
        raise SystemExit(f"PDF 가 없음: {args.dir}")

    parsed = [parse_pdf(p) for p in files]
    unify_course_names(parsed)
    print("학과 홈페이지 교수 목록 조회 중...")
    faculty = fetch_faculty()
    print(f"  교수 {len(faculty)}명 (이메일 {sum(1 for f in faculty if f['email'])}명)\n")

    print(f"{'파일':<16} {'과목명':<22} {'학점':>2} {'요일':<4} {'시간':<11} {'학년':<7} {'교수(출처)'}")
    for pc in parsed:
        name, src = resolve_professor(pc, faculty)
        t = f"{pc.class_start_time}~{pc.class_end_time}" if pc.class_start_time else "-"
        print(f"{pc.course_code}_{pc.section:02d}".ljust(16),
              (pc.course_name or "-")[:22].ljust(22), str(pc.credits).rjust(2),
              (pc.class_days or "-").ljust(4), t.ljust(11), (pc.target_grade or "-").ljust(7),
              f"{name} ({src})")

    missing = [pc.filename for pc in parsed if not (pc.course_name and pc.class_days and pc.class_start_time)]
    print(f"\n강의 {len(parsed)}개 / 과목 {len({pc.course_code for pc in parsed})}개 / 누락 필드 있는 PDF {len(missing)}개")
    for f in missing:
        print("  - 누락:", f)

    if args.summarize:
        from app.services.syllabus_service import OLLAMA_URL
        print(f"\nAI 요약 시작 (OLLAMA_URL={OLLAMA_URL})")
        print("요약 결과:", summarize(files, parsed, faculty, args.force))
        return
    if not args.apply:
        print("\n[dry-run] DB 에 쓰지 않았습니다. 적재하려면 --apply")
        return
    print("\n적재 결과:", apply(parsed, faculty))


if __name__ == "__main__":
    main()
