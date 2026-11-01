import os
import secrets

import redis

from app.services.email_service import send_verification_email

# redis로 연결
redis_client = redis.StrictRedis(host='redis', port=6379, db=0, decode_responses=True)

OTP_TTL = 180            # 코드 유효 3분
MAX_ATTEMPTS = 5         # 코드당 검증 시도 한도 — 넘으면 코드 폐기 (무차별 대입 방지)


def _generate_otp() -> str:
    # 6자리 OTP — 추측을 어렵게 암호학적 난수 사용 (random 모듈은 예측 가능)
    return f"{secrets.randbelow(1_000_000):06d}"


def _check_otp(key: str, code: str) -> bool:
    """저장된 코드와 비교. 틀린 시도가 MAX_ATTEMPTS 를 넘으면 코드를 폐기한다.

    시도 횟수는 코드와 같은 TTL 로 같이 만료된다. 성공하면 코드와 카운터를 모두 지운다.
    6자리(100만 경우) 코드를 3분 안에 5번까지만 넣을 수 있어 무차별 대입이 불가능하다.
    """
    saved = redis_client.get(key)
    if saved is None:
        return False  # 없거나 만료됨

    attempts_key = f"attempts:{key}"
    if (redis_client.get(attempts_key) or 0) and int(redis_client.get(attempts_key)) >= MAX_ATTEMPTS:
        redis_client.delete(key, attempts_key)  # 시도 초과 — 코드 폐기, 재발급 필요
        return False

    if secrets.compare_digest(saved, code):
        redis_client.delete(key, attempts_key)
        return True

    # 실패 — 시도 횟수 증가 (코드 TTL 과 함께 만료)
    n = redis_client.incr(attempts_key)
    if n == 1:
        redis_client.expire(attempts_key, OTP_TTL)
    if n >= MAX_ATTEMPTS:
        redis_client.delete(key, attempts_key)
    return False


def request_email_verification(email: str, background_tasks):
    auth_code = _generate_otp()
    redis_client.set(email, auth_code, ex=OTP_TTL)
    redis_client.delete(f"attempts:{email}")  # 재발급 시 이전 시도 횟수 초기화
    background_tasks.add_task(send_verification_email, email, auth_code)


def verify_auth_code(email: str, code: str):  # 인증 성공 시 코드 삭제
    if _check_otp(email, code):
        return {"success": True, "message": "인증에 성공했습니다!"}
    return {"success": False, "message": "인증번호가 일치하지 않거나 만료되었습니다."}


def request_password_reset(email: str, background_tasks):
    auth_code = _generate_otp()
    redis_client.set(f"reset:{email}", auth_code, ex=OTP_TTL)  # 회원가입 OTP와 키 분리
    redis_client.delete(f"attempts:reset:{email}")
    background_tasks.add_task(send_verification_email, email, auth_code)


def verify_reset_code(email: str, code: str) -> bool:
    return _check_otp(f"reset:{email}", code)
