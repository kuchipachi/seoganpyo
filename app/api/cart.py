from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.database import get_db
from app.dependencies import get_current_student_id
from app.models.activity import Cart
from app.models.course import Course
from app.schemas.cart import CartCreate, CartResponse

router = APIRouter(prefix="/api/v1", tags=["Cart"])


# 장바구니는 토큰의 학번으로만 접근한다 (get_current_student_id).
# 학번을 경로로 받던 옛 경로(/users/{student_id}/cart·history)는 본인 확인이 없어 제거했다.
# 수강이력은 app/api/history.py (/history/me 등).

@router.get("/cart", response_model=List[CartResponse])
def get_my_cart(
    student_id: int = Depends(get_current_student_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(Cart)
        .options(joinedload(Cart.course).joinedload(Course.professor))
        .filter(Cart.student_id == student_id)
        .all()
    )


@router.post("/cart", response_model=CartResponse, status_code=201)
def add_to_my_cart(
    req: CartCreate,
    student_id: int = Depends(get_current_student_id),
    db: Session = Depends(get_db),
):
    exists = db.query(Cart).filter(
        Cart.student_id == student_id,
        Cart.course_id == req.course_id,
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="이미 장바구니에 담긴 강의입니다.")
    if not db.query(Course).filter(Course.course_id == req.course_id).first():
        raise HTTPException(status_code=404, detail="강의를 찾을 수 없습니다.")
    cart_item = Cart(student_id=student_id, course_id=req.course_id)
    db.add(cart_item)
    db.commit()
    db.refresh(cart_item)
    return cart_item


@router.delete("/cart/{cart_id}", status_code=204)
def remove_from_my_cart(
    cart_id: int,
    student_id: int = Depends(get_current_student_id),
    db: Session = Depends(get_db),
):
    cart_item = db.query(Cart).filter(
        Cart.id == cart_id,
        Cart.student_id == student_id,
    ).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="장바구니 항목을 찾을 수 없습니다.")
    db.delete(cart_item)
    db.commit()
