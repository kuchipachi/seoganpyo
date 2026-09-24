"""scripts/seed_courses_from_syllabi.py 파싱 규칙 테스트.

PDF 원본은 레포에 없으므로(.gitignore), 실제 강의계획서 첫 장에서 뽑은 문구를 입력으로 쓴다.
"""
from scripts.seed_courses_from_syllabi import (
    ParsedCourse,
    _clean_person,
    _parse_days,
    _parse_grade,
    _parse_times,
    _schedule_segment,
    resolve_professor,
    unify_course_names,
)


def _days_times(header: str):
    seg = _schedule_segment(header)
    return _parse_days(seg), _parse_times(seg)


def test_korean_schedule():
    assert _days_times("수업시간 월/수 12:00~13:15 (1분반) 수강대상 학부 1학년") == ("월수", ("12:00", "13:15"))
    assert _days_times("수업시간 월,수 10:30~11:45 강의실") == ("월수", ("10:30", "11:45"))


def test_schedule_does_not_leak_into_next_field():
    # '수강대상' 의 '수' 가 수요일로 잡히면 안 됨
    assert _days_times("수업시간 화 15:00 ~ 20:50 수강대상 2학년") == ("화", ("15:00", "20:50"))


def test_yoil_suffix_is_not_sunday():
    # '월요일' 의 '일' 이 일요일로 잡히면 안 됨
    assert _days_times("수업시간 월요일(13:30~16:15) 수강대상 3/4 학년")[0] == "월"


def test_multiple_day_time_pairs():
    assert _days_times("Class Time 수13:30~14:45, 금13:30~14:45 Classroom 추후 공지")[0] == "수금"


def test_english_schedules():
    assert _days_times("Meeting Times Tuesday and Thursday (13:30 ~ 14:45) Classroom TBD") == ("화목", ("13:30", "14:45"))
    assert _days_times("Class Time Tue/Thu 10:30~11:45 Enrollment") == ("화목", ("10:30", "11:45"))
    assert _days_times("Class Time WF 13:30-14:45 Classroom tba")[0] == "수금"


def test_am_suffix_and_single_digit_hour():
    assert _parse_times("수/금 9:00~10:15AM") == ("09:00", "10:15")


def test_grades():
    assert _parse_grade("수강대상 3-4학년 수업시간") == "3,4"
    assert _parse_grade("수강대상 학년3-4 담당교수") == "3,4"
    assert _parse_grade("수강대상 2~4학년 담당교수") == "2,3,4"
    assert _parse_grade("Enrollment Eligibility Sophomore (2nd-year) and Junior (3rd-year) Meeting") == "2,3"
    assert _parse_grade("수강대상 Undergraduate (CS/AI) 담당교수") is None


def test_clean_person():
    assert _clean_person("문 의 현 ") == "문의현"
    assert _clean_person("Youngmin Yi (이영민) ") == "이영민"
    assert _clean_person("김주호 (Juho Kim) ") == "김주호"
    assert _clean_person("손진호교수 ") == "손진호"
    assert _clean_person("Joo Ho Lee ") == "Joo Ho Lee"


def _pc(code, section, name, prof=None, email=None):
    return ParsedCourse(
        filename=f"2026-1학기__{code}_{section:02d}.pdf", year=2026, semester=1,
        course_code=code, section=section, course_name=name, credits=3,
        class_days="월수", class_start_time="12:00", class_end_time="13:15",
        target_grade=None, professor_name=prof, professor_email=email,
    )


def test_unify_course_names_prefers_korean():
    group = [_pc("CSE2003", 2, "Computer Programming I"), _pc("CSE2003", 1, "컴퓨터프로그래밍I")]
    unify_course_names(group)
    assert {pc.course_name for pc in group} == {"컴퓨터프로그래밍I"}


def test_resolve_professor_by_email_over_english_name():
    faculty = [{"name": "이주호", "email": "jhleecs@sogang.ac.kr"}]
    assert resolve_professor(_pc("CSE2003", 3, "x", "Joo Ho Lee", "jhleecs@sogang.ac.kr"), faculty) == ("이주호", "email")
    assert resolve_professor(_pc("CSE4020", 1, "x", "최수진", "sujinchoi@sogang.ac.kr"), faculty) == ("최수진", "pdf")
