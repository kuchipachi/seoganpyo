"""사용자 입력이 HTML·메일 헤더에 그대로 들어가지 않는지 (XSS·헤더 주입 방지).

회원가입 이름·이메일과 문의 제목·내용은 사용자가 정한 값이다. 이걸 이스케이프 없이
승인 완료 화면(관리자 브라우저, 사이트와 같은 도메인)이나 메일 본문·제목에 넣으면
스크립트·가짜 링크·헤더를 끼워 넣을 수 있다.
"""
from unittest.mock import patch

from app.services import email_service

MARK = "<b>x</b>"          # 태그가 살아 있으면 이스케이프 실패
ESCAPED = "&lt;b&gt;x&lt;/b&gt;"


def _register_pending(db, name=MARK):
    from app.models.user import User
    from app.services.user_service import hash_password
    u = User(student_id=20219999, name=name, email="pending@sogang.ac.kr",
             password=hash_password("Passw0rd!"), is_approved=False, approval_token="tok-123")
    db.add(u)
    db.commit()
    return u


def test_approve_page_escapes_user_fields(client, db):
    _register_pending(db)
    res = client.get("/auth/approve", params={"token": "tok-123"})
    assert res.status_code == 200
    assert MARK not in res.text
    assert ESCAPED in res.text


class _Capture:
    """smtplib.SMTP 대역 — 보낸 메시지를 붙잡는다"""
    sent = []

    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): pass
    def login(self, *a): pass
    def sendmail(self, frm, to, msg): _Capture.sent.append(msg)
    def send_message(self, msg, *a, **k): _Capture.sent.append(msg.as_string())


def _send(fn, *args):
    _Capture.sent = []
    with patch.object(email_service.smtplib, "SMTP", _Capture), \
         patch.dict("os.environ", {"SENDER_EMAIL": "bot@sogang.ac.kr", "SENDER_PASSWORD": "x"}):
        fn(*args)
    assert _Capture.sent, "메일이 발송되지 않음"
    return _Capture.sent[0]


def _html_part(raw: str) -> str:
    import email
    msg = email.message_from_string(raw)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode()
    raise AssertionError("HTML 본문 없음")


def test_approval_email_escapes_and_strips_header_newlines():
    raw = _send(email_service.send_approval_request_email,
                MARK + "\r\nBcc: evil@example.com", "a@sogang.ac.kr", 20219999, "https://x/approve?token=t&a=1")
    import email
    msg = email.message_from_string(raw)
    assert msg["Bcc"] is None                      # 제목 줄바꿈으로 헤더를 끼워 넣을 수 없다
    body = _html_part(raw)
    assert MARK not in body and ESCAPED in body


def test_contact_email_escapes_user_fields():
    raw = _send(email_service.send_contact_email, MARK, MARK, MARK, "a@sogang.ac.kr")
    body = _html_part(raw)
    assert MARK not in body
    assert body.count(ESCAPED) >= 3                # 제목·내용·보낸 사람
