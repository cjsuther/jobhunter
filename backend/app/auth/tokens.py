"""JWT token issuing and verification."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from jose import JWTError, jwt

from app.config import get_settings


class TokenError(Exception):
    pass


TokenType = Literal["access", "refresh"]


def _now() -> datetime:
    return datetime.now(UTC)


def create_token(user_id: UUID, role: str, kind: TokenType) -> str:
    settings = get_settings()
    if kind == "access":
        exp = _now() + timedelta(minutes=settings.jwt_access_ttl_min)
    else:
        exp = _now() + timedelta(days=settings.jwt_refresh_ttl_days)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": kind,
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected: TokenType | None = None) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise TokenError(f"invalid token: {e}") from e
    if expected and payload.get("type") != expected:
        raise TokenError(f"token type mismatch: expected {expected}, got {payload.get('type')}")
    return payload
