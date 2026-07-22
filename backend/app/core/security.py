from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _encode_token(
    *,
    user_id: UUID,
    email: str,
    token_type: TokenType,
    expire_minutes: int,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "exp": now + timedelta(minutes=expire_minutes),
        "iat": now,
        "type": token_type,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(*, user_id: UUID, email: str) -> str:
    settings = get_settings()
    return _encode_token(
        user_id=user_id,
        email=email,
        token_type="access",
        expire_minutes=settings.access_token_expire_minutes,
    )


def create_refresh_token(*, user_id: UUID, email: str) -> str:
    settings = get_settings()
    return _encode_token(
        user_id=user_id,
        email=email,
        token_type="refresh",
        expire_minutes=settings.refresh_token_expire_minutes,
    )


def create_token_pair(*, user_id: UUID, email: str) -> tuple[str, str]:
    return (
        create_access_token(user_id=user_id, email=email),
        create_refresh_token(user_id=user_id, email=email),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"expected token type {expected_type!r}")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode an access token (rejects refresh tokens)."""
    return decode_token(token, expected_type="access")
