"""Per-user account settings — API keys, etc."""

from __future__ import annotations

from datetime import datetime

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import get_db
from app.logging_setup import get_logger
from app.models.user import User
from app.models.user_secret import UserSecret
from app.services.api_keys import (
    delete_anthropic_key,
    mask,
    record_validation,
    resolve_anthropic_key,
    set_anthropic_key,
)
from app.services.encryption import decrypt_str

router = APIRouter()
log = get_logger("app.routers.account")


class AnthropicKeyStatus(BaseModel):
    configured: bool
    source: str  # "db" | "env" | "none"
    masked_key: str | None
    last_validated_at: datetime | None
    last_validated_ok: bool | None


class AnthropicKeyUpdate(BaseModel):
    api_key: str


class TestResult(BaseModel):
    ok: bool
    detail: str | None = None


@router.get("/anthropic-key", response_model=AnthropicKeyStatus)
def get_anthropic_key_status(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> AnthropicKeyStatus:
    row = db.get(UserSecret, current.id)
    if row and row.anthropic_api_key_encrypted:
        key = decrypt_str(row.anthropic_api_key_encrypted)
        return AnthropicKeyStatus(
            configured=True,
            source="db",
            masked_key=mask(key),
            last_validated_at=row.last_validated_at,
            last_validated_ok=row.last_validated_ok,
        )
    # Fall back to env — only report it if it looks real (not the placeholder).
    env_key = (get_settings().anthropic_api_key or "").strip()
    if env_key and env_key not in {"sk-ant-REPLACE_ME", "sk-ant-xxxxx"}:
        return AnthropicKeyStatus(
            configured=True,
            source="env",
            masked_key=mask(env_key),
            last_validated_at=None,
            last_validated_ok=None,
        )
    return AnthropicKeyStatus(
        configured=False, source="none", masked_key=None,
        last_validated_at=None, last_validated_ok=None,
    )


@router.put("/anthropic-key", response_model=AnthropicKeyStatus)
def update_anthropic_key(
    payload: AnthropicKeyUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> AnthropicKeyStatus:
    if not payload.api_key.strip().startswith("sk-ant-"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "el formato esperado es 'sk-ant-...'",
        )
    set_anthropic_key(current.id, payload.api_key)
    return get_anthropic_key_status(db=db, current=current)


@router.delete("/anthropic-key", status_code=status.HTTP_204_NO_CONTENT)
def remove_anthropic_key(
    current: User = Depends(get_current_user),
) -> None:
    delete_anthropic_key(current.id)


@router.post("/anthropic-key/test", response_model=TestResult)
async def test_anthropic_key(
    current: User = Depends(get_current_user),
) -> TestResult:
    """Send a 1-token ping to Anthropic with the user's effective key.

    Costs ~$0.0001 (1 input token + 1 output token, Haiku).
    """
    key = resolve_anthropic_key(current.id)
    if not key:
        return TestResult(ok=False, detail="no hay key configurada")

    try:
        client = AsyncAnthropic(api_key=key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        # Any non-error response means the key works.
        _ = getattr(resp, "id", None)
        record_validation(current.id, True)
        return TestResult(ok=True, detail="key válida")
    except Exception as e:  # noqa: BLE001
        log.warning("account.key_test_failed", user_id=str(current.id), error=str(e))
        record_validation(current.id, False)
        return TestResult(ok=False, detail=str(e)[:200])
