"""웹앱/안드로이드 앱용 자체 계정 인증 (이메일/비밀번호 + JWT).

카카오톡 봇과는 완전히 독립된 인증 체계다. 카카오 쪽은 plusfriendUserKey를
kakao_user_id로 그대로 쓰고, 이 앱은 여기서 발급한 정수 user id를 owner_id
문자열로 변환해(``app_user_owner_id``) 같은 receipts 테이블을 공유한다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any

import jwt
from fastapi import Header, HTTPException

PBKDF2_ITERATIONS = 260_000
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30일


class AuthError(Exception):
    """인증 관련 실패 (회원가입/로그인/토큰 검증)."""


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_str, salt, expected_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(digest.hex(), expected_hex)


def _jwt_secret() -> str:
    secret = (
        os.environ.get("JWT_SECRET")
        or os.environ.get("REPORT_SIGNING_SECRET")
        or os.environ.get("WEBHOOK_SECRET")
    )
    if not secret:
        raise AuthError("JWT_SECRET(또는 REPORT_SIGNING_SECRET) 환경변수 필요")
    return secret


def owner_id_for_user(user_id: int) -> str:
    """웹/앱 사용자를 receipts.kakao_user_id 컬럼과 공유하기 위한 고유 접두사.

    카카오의 plusfriendUserKey(긴 해시 문자열)와 절대 충돌하지 않도록 고정 접두사를 붙인다.
    """
    return f"app_user:{user_id}"


def create_access_token(user_id: int, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError("유효하지 않거나 만료된 토큰입니다.") from exc


def get_current_user_id(authorization: str | None = Header(default=None)) -> int:
    """FastAPI Depends용: Authorization: Bearer <token> 검증 후 user id 반환."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
        return int(payload["sub"])
    except (AuthError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.") from exc
