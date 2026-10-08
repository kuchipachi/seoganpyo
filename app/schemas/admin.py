from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ReportCountsResponse(BaseModel):
    total: int
    욕설: int
    스팸: int
    기타: int


class ReportItem(BaseModel):
    id: int
    reporter_id: Optional[int] = None
    reporter_name: Optional[str] = None
    target_type: str
    target_id: int
    target_title: Optional[str] = None
    target_content: Optional[str] = None
    target_author: Optional[str] = None
    target_category: Optional[str] = None
    reason: str
    detail: Optional[str] = None
    status: str
    created_at: datetime


class ReportActionResponse(BaseModel):
    message: str
    report_id: int


class ContactCountsResponse(BaseModel):
    total: int


class ContactItem(BaseModel):
    id: int
    student_id: Optional[int] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    subject: str
    content: str
    status: str
    created_at: datetime


class MessageResponse(BaseModel):
    message: str


class UserListItem(BaseModel):
    student_id: int
    name: str
    email: str
    role: str
    can_post: bool
    can_comment: bool
    current_semester: Optional[int] = None


class CanPostResponse(BaseModel):
    student_id: int
    can_post: bool


class CanCommentResponse(BaseModel):
    student_id: int
    can_comment: bool


class AdminMessageCreate(BaseModel):
    content: str


class AdminMessageItem(BaseModel):
    id: int
    content: str
    sender_name: Optional[str] = None
    created_at: datetime


class UserInfoResponse(BaseModel):
    student_id: int
    name: str
    email: str
    current_semester: Optional[int] = None


class PendingUserItem(BaseModel):
    """이메일 인증은 끝났지만 관리자 승인 대기 중인 사용자."""
    student_id: int
    name: str
    email: str
    current_semester: Optional[int] = None


class ApproveUserResponse(BaseModel):
    student_id: int
    is_approved: bool


class MetricPoint(BaseModel):
    t: int                    # epoch 초
    v: Optional[float] = None  # 데이터 없음(NaN)이면 None


class AdminMetricsResponse(BaseModel):
    """관리자 모니터링 — 사용자 요청 기준 API 메트릭 (/metrics·헬스체크 제외)"""
    range: str
    step_seconds: int
    rps: list[MetricPoint]
    p95_ms: list[MetricPoint]
    errors_5xx_rps: list[MetricPoint]
    total_requests: Optional[float] = None
    total_5xx: Optional[float] = None
    api_up: Optional[bool] = None
