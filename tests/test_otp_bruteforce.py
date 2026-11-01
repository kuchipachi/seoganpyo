"""OTP 무차별 대입 방지 — 틀린 시도가 한도를 넘으면 코드가 폐기된다 (보안 점검 2026-11)."""
import fakeredis
import pytest

from app.services import auth_service as a


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(a, "redis_client", r)
    return r


class _Tasks:
    def add_task(self, *a, **k): pass


def test_correct_code_succeeds(monkeypatch, fake_redis):
    monkeypatch.setattr(a.secrets, "randbelow", lambda n: 123456)
    a.request_email_verification("u@sogang.ac.kr", _Tasks())
    assert a.verify_auth_code("u@sogang.ac.kr", "123456")["success"] is True


def test_code_burned_after_max_attempts(monkeypatch, fake_redis):
    monkeypatch.setattr(a.secrets, "randbelow", lambda n: 123456)
    a.request_email_verification("u@sogang.ac.kr", _Tasks())
    for _ in range(a.MAX_ATTEMPTS):
        assert a.verify_auth_code("u@sogang.ac.kr", "000000")["success"] is False
    # 한도 초과 후에는 올바른 코드도 통하지 않는다 (폐기됨)
    assert a.verify_auth_code("u@sogang.ac.kr", "123456")["success"] is False


def test_reissue_resets_attempts(monkeypatch, fake_redis):
    monkeypatch.setattr(a.secrets, "randbelow", lambda n: 111111)
    a.request_email_verification("u@sogang.ac.kr", _Tasks())
    for _ in range(a.MAX_ATTEMPTS - 1):
        a.verify_auth_code("u@sogang.ac.kr", "000000")
    a.request_email_verification("u@sogang.ac.kr", _Tasks())  # 재발급 → 시도 초기화
    assert a.verify_auth_code("u@sogang.ac.kr", "111111")["success"] is True


def test_reset_code_brute_force_blocked(monkeypatch, fake_redis):
    monkeypatch.setattr(a.secrets, "randbelow", lambda n: 222222)
    a.request_password_reset("u@sogang.ac.kr", _Tasks())
    for _ in range(a.MAX_ATTEMPTS):
        assert a.verify_reset_code("u@sogang.ac.kr", "999999") is False
    assert a.verify_reset_code("u@sogang.ac.kr", "222222") is False


def test_missing_or_expired_code(fake_redis):
    assert a.verify_auth_code("none@sogang.ac.kr", "123456")["success"] is False
    assert a.verify_reset_code("none@sogang.ac.kr", "123456") is False
