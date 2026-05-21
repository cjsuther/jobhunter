"""Resolve and persist per-user API keys (Anthropic for now).

Resolution order when an LLM call needs a key:
1. The user's DB-stored key (encrypted with Fernet at rest).
2. The global `ANTHROPIC_API_KEY` env var, as a fallback.

This lets each user supply their own key from the UI while keeping the env
fallback working for fresh installs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.config import get_settings
from app.db import SessionLocal
from app.logging_setup import get_logger
from app.models.user_secret import UserSecret
from app.services.encryption import decrypt_str, encrypt_str

log = get_logger("app.services.api_keys")


_ENV_PLACEHOLDERS = {"", "sk-ant-REPLACE_ME", "sk-ant-xxxxx"}


def _env_key() -> str | None:
    s = get_settings()
    k = (s.anthropic_api_key or "").strip()
    return k if k not in _ENV_PLACEHOLDERS else None


def resolve_anthropic_key(user_id: UUID | None) -> str | None:
    """Return the Anthropic key to use for this user.

    DB-stored value wins. Falls back to env. Returns None if neither is set.
    Workers and HTTP handlers MUST pass a user_id when possible — without it
    we can only use the env fallback (e.g. background admin tooling).
    """
    if user_id is not None:
        try:
            with SessionLocal() as db:
                row = db.get(UserSecret, user_id)
                if row and row.anthropic_api_key_encrypted:
                    return decrypt_str(row.anthropic_api_key_encrypted)
        except Exception as e:  # noqa: BLE001
            log.warning("api_keys.db_lookup_failed", error=str(e), user_id=str(user_id))
    return _env_key()


def set_anthropic_key(user_id: UUID, key: str) -> None:
    """Store (encrypted) the user's Anthropic key. Overwrites if it existed."""
    key = key.strip()
    if not key:
        raise ValueError("empty key")
    with SessionLocal() as db:
        row = db.get(UserSecret, user_id)
        if row is None:
            row = UserSecret(user_id=user_id)
            db.add(row)
        row.anthropic_api_key_encrypted = encrypt_str(key)
        row.last_validated_at = None
        row.last_validated_ok = None
        db.commit()


def delete_anthropic_key(user_id: UUID) -> None:
    with SessionLocal() as db:
        row = db.get(UserSecret, user_id)
        if row is None:
            return
        row.anthropic_api_key_encrypted = None
        row.last_validated_at = None
        row.last_validated_ok = None
        db.commit()


def record_validation(user_id: UUID, ok: bool) -> None:
    with SessionLocal() as db:
        row = db.get(UserSecret, user_id)
        if row is None:
            return
        row.last_validated_at = datetime.now(UTC)
        row.last_validated_ok = ok
        db.commit()


def mask(key: str) -> str:
    """Render a key as `sk-ant-...XYZW` for display."""
    if not key:
        return ""
    if len(key) <= 12:
        return "***"
    return f"{key[:8]}…{key[-4:]}"
