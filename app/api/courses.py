from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload
from typing import List, Optional
from app.database import get_db
from app.models.course import Course
from app.models.professor import Professor
from app.schemas.course import CourseResponse

router = APIRouter(prefix="/api/v1/courses", tags=["Courses"])


@router.get("", response_model=List[CourseResponse])
def get_courses(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="강의명, 강의코드, 또는 교수명 검색"),
    year: Optional[int] = Query(None),
    semester: Optional[int] = Query(None),
    category: Optional[str] = Query(None, description="course_category 필터"),
    division: Optional[str] = Query(
        None,
        regex="^(major|liberal)$",
        description="major=CSE 전공, liberal=교양 (course_code prefix 기준)",
    ),
    is_english: Optional[bool] = Query(None),
    limit: Optional[int] = Query(None),
    offset: int = Query(0),
):
    # CourseResponse 는 course.details · professor.details 까지 직렬화한다.
    # 미리 불러오지 않으면 응답 변환 중 강의·교수마다 지연 로딩 쿼리가 나가(N+1)
    # 37강의 기준 요청당 SQL 64개가 되고, 그동안 DB 연결을 쥐고 있어 교착 조건을 만든다
    # (docs/postmortems/2026-09-27-db-pool-deadlock.md). selectinload 로 IN (...) 한 번씩 → 3개.
    query = db.query(Course).options(
        joinedload(Course.professor).selectinload(Professor.details),
        selectinload(Course.details),
    )
    if q:
        query = query.join(Professor, Course.professor_id == Professor.professor_id, isouter=True).filter(
            Course.course_name.ilike(f"%{q}%")
            | Course.course_code.ilike(f"%{q}%")
            | Professor.name.ilike(f"%{q}%")
        )
    if year:
        query = query.filter(Course.year == year)
    if semester:
        query = query.filter(Course.semester == semester)
    if category:
        query = query.filter(Course.course_category == category)
    if division == "major":
        query = query.filter(Course.course_code.like("CSE%"))
    elif division == "liberal":
        query = query.filter(~Course.course_code.like("CSE%"))
    if is_english is not None:
        query = query.filter(Course.is_english == is_english)
    query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    return query.all()


@router.get("/code/{course_code}", response_model=CourseResponse)
def get_course_by_code(course_code: str, db: Session = Depends(get_db)):
    course = (
        db.query(Course)
        .options(
            joinedload(Course.professor).joinedload(Professor.details),
            joinedload(Course.details),
        )
        .filter(Course.course_code == course_code)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")
    return course


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(course_id: int, db: Session = Depends(get_db)):
    course = (
        db.query(Course)
        .options(
            joinedload(Course.professor).joinedload(Professor.details),
            joinedload(Course.details),
        )
        .filter(Course.course_id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")
    return course
