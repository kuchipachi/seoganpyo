import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_student_id
from app.models.course import Course, CourseDetail
from app.schemas.syllabus import SyllabusSummaryResponse
from app.services import syllabus_service

def _find_pdf_by_hash(target_hash: str) -> Optional[Path]:
    syllabi_dir = Path("data/syllabi")
    if syllabi_dir.exists():
        for f in syllabi_dir.glob("*.pdf"):
            if hashlib.sha256(f.read_bytes()).hexdigest() == target_hash:
                return f
    return None

router = APIRouter(prefix="/api/v1/syllabus", tags=["Syllabus"])


def _build_response(detail: CourseDetail, course: Course, cached: bool) -> SyllabusSummaryResponse:
    return SyllabusSummaryResponse(
        course_id=detail.course_id,
        course_code=course.course_code if course else None,
        year=course.year if course else None,
        semester=course.semester if course else None,
        overview=detail.overview,
        goals=detail.required_skills,
        evaluation_method=detail.evaluation_method,
        cached=cached,
    )


@router.post("/summarize", response_model=SyllabusSummaryResponse, status_code=200)
async def summarize_syllabus(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    student_id: int = Depends(get_current_student_id),  # 로그인 사용자만 — 비인증 LLM 호출 남용 방지
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다")

    file_bytes = await file.read()
    detail, course, cached = syllabus_service.process_syllabus(db, file_bytes)
    return _build_response(detail, course, cached)


@router.get("/{course_id}/pdf/{filename:path}", include_in_schema=False)
@router.get("/{course_id}/pdf")
def get_syllabus_pdf(course_id: int, db: Session = Depends(get_db), filename: str = ""):
    detail = db.query(CourseDetail).filter(CourseDetail.course_id == course_id).first()
    if not detail or not detail.pdf_hash:
        raise HTTPException(status_code=404, detail="강의계획서 PDF가 없습니다")

    pdf_path = _find_pdf_by_hash(detail.pdf_hash)
    if not pdf_path:
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다")

    from urllib.parse import quote
    course = db.query(Course).filter(Course.course_id == course_id).first()
    filename = f"{course.course_name} 강의계획서.pdf" if course else "강의계획서.pdf"
    encoded = quote(filename, safe="")
    content = pdf_path.read_bytes()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded}"},
    )


@router.get("/{course_id}", response_model=SyllabusSummaryResponse)
def get_syllabus_summary(course_id: int, db: Session = Depends(get_db)):
    detail = db.query(CourseDetail).filter(CourseDetail.course_id == course_id).first()
    if not detail or not detail.overview:
        raise HTTPException(status_code=404, detail="저장된 요약이 없습니다")

    course = db.query(Course).filter(Course.course_id == course_id).first()
    return _build_response(detail, course, cached=True)
