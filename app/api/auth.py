import html
import os
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from app.services import auth_service
from app.services import discord_service
from app.services import email_service
from app.services import user_service
from app.schemas.auth import EmailRequest, VerifyRequest, ResetPasswordRequest
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.database import get_db

# 라우터 설정
router = APIRouter(prefix="/auth", tags=["User Authentication"])

@router.post("/send-email")
async def send_email(request: EmailRequest, background_tasks: BackgroundTasks):
    email = request.email
    
    # 서강대 이메일 형식 체크
    if not email.endswith("@sogang.ac.kr"):
        return JSONResponse(
            status_code=400,
            content={"message": "서강대학교 이메일(@sogang.ac.kr)만 사용 가능합니다."},
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
    
    # 이메일 발송 로직 호출 (백그라운드 실행)
    auth_service.request_email_verification(email, background_tasks)
    
    return JSONResponse(
        content={"message": f"{email}로 인증번호가 발송되었습니다. (3분 유효)"},
        headers={"Content-Type": "application/json; charset=utf-8"}
    )

@router.post("/verify-code")
async def verify_code(request: VerifyRequest):
    # request 바구니에서 이메일과 코드를 꺼내서 검증합니다.
    result = auth_service.verify_auth_code(request.email, request.code)

    if not result["success"]:
        return JSONResponse(
            status_code=400,
            content={"message": result["message"]},
            headers={"Content-Type": "application/json; charset=utf-8"}
        )

    return JSONResponse(
        content={"message": result["message"]},
        headers={"Content-Type": "application/json; charset=utf-8"}
    )


@router.post("/register", response_model=UserResponse, status_code=201)
def register(req: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if user_service.get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")
    if user_service.get_user_by_id(db, req.student_id):
        raise HTTPException(status_code=409, detail="이미 등록된 학번입니다.")
    token = str(uuid.uuid4())
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8080")
    approval_url = f"{backend_url}/auth/approve?token={token}"
    user = user_service.create_user(
        db,
        student_id=req.student_id,
        name=req.name,
        email=req.email,
        password=req.password,
        current_semester=req.current_semester,
        major_credits=req.major_credits,
        common_credits=req.common_credits,
        total_credits=req.total_credits,
        total_english=req.total_english,
        is_approved=False,
        approval_token=token,
    )
    background_tasks.add_task(
        email_service.send_approval_request_email,
        req.name, req.email, req.student_id, approval_url,
    )
    # Discord 알림 — admin 이 신청 놓치지 않게. webhook 미설정/실패해도 회원가입은 정상 진행.
    background_tasks.add_task(
        discord_service.send_signup_notification,
        req.name, req.student_id, req.email,
    )
    return user


@router.get("/approve", response_class=HTMLResponse)
def approve_user(token: str, db: Session = Depends(get_db)):
    user = user_service.get_user_by_approval_token(db, token)
    if not user:
        return HTMLResponse(
            content="<html><body style='font-family:sans-serif;text-align:center;padding:50px'><h2>유효하지 않거나 이미 처리된 승인 링크입니다.</h2></body></html>",
            status_code=404,
        )
    user.is_approved = True
    user.approval_token = None
    db.commit()
    return HTMLResponse(content=f"""
    <html>
    <head><title>회원가입 승인 완료</title></head>
    <body style="font-family:'Malgun Gothic',sans-serif;text-align:center;padding:60px;color:#333;">
        <h1 style="color:#B1000E;">서간표</h1>
        <h2>회원가입 승인 완료</h2>
        <p><strong>{html.escape(user.name)}</strong> ({html.escape(user.email)}) 님의 가입이 승인되었습니다.</p>
        <p style="color:#666;">이제 해당 사용자가 서간표에 로그인할 수 있습니다.</p>
    </body>
    </html>
    """)


@router.post("/login", response_model=Token)
def login(req: UserLogin, db: Session = Depends(get_db)):
    user = user_service.get_user_by_email(db, req.email)
    if not user:
        raise HTTPException(status_code=404, detail="가입된 이메일이 없습니다.")
    if not user_service.verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="비밀번호가 틀렸습니다.")
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="승인 대기 중입니다. 관리자 승인 후 로그인할 수 있습니다.")
    token = user_service.create_access_token(user.student_id)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/reset-password/send-email")
async def reset_password_send_email(request: EmailRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not user_service.get_user_by_email(db, request.email):
        raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")
    auth_service.request_password_reset(request.email, background_tasks)
    return JSONResponse(
        content={"message": f"{request.email}로 인증번호가 발송되었습니다. (3분 유효)"},
        headers={"Content-Type": "application/json; charset=utf-8"}
    )


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    if not user_service.get_user_by_email(db, request.email):
        raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")
    if not auth_service.verify_reset_code(request.email, request.code):
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않거나 만료되었습니다.")
    user_service.update_password(db, request.email, request.new_password)
    return JSONResponse(
        content={"message": "비밀번호가 변경되었습니다."},
        headers={"Content-Type": "application/json; charset=utf-8"}
    )