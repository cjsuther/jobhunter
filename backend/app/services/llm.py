"""Anthropic SDK wrapper with retry, prompt cache wiring, and cost tracking.

Models:
- scoring: claude-haiku-4-5-20251001 (cheap, used per-job)
- generation: claude-sonnet-4-6 (CVs, cover letters)

Every call is persisted to the `llm_calls` table with model, purpose, token
usage and computed USD cost — feeds the cost dashboard.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.logging_setup import get_logger
from app.services.api_keys import resolve_anthropic_key
from app.services.llm_pricing import compute_cost_usd

log = get_logger("app.services.llm")


class AnthropicKeyMissing(RuntimeError):
    """Raised when no usable Anthropic key is configured for the caller."""


def _client(user_id: UUID | None = None) -> AsyncAnthropic:
    key = resolve_anthropic_key(user_id)
    if not key:
        raise AnthropicKeyMissing(
            "No hay API key de Anthropic configurada. "
            "Configurala en Settings → Cuenta o en .env."
        )
    return AsyncAnthropic(api_key=key)


def _record_call(
    *,
    user_id: UUID | None,
    model: str,
    purpose: str,
    usage: Any,
) -> None:
    """Persist a single LLM call to the database. Best-effort: any failure here
    must NOT break the actual API response.
    """
    try:
        # Anthropic SDK exposes usage as an object with these int fields. Some
        # may be absent for cache misses → default to 0.
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)
        cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cost = compute_cost_usd(
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_creation_input_tokens=cw,
            cache_read_input_tokens=cr,
        )

        # Lazy imports to avoid circulars and keep this module cheap to import.
        from app.db import SessionLocal
        from app.models.llm_call import LLMCall

        with SessionLocal() as db:
            db.add(
                LLMCall(
                    user_id=user_id,
                    model=model,
                    purpose=purpose,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cache_creation_input_tokens=cw,
                    cache_read_input_tokens=cr,
                    cost_usd=cost,
                )
            )
            db.commit()

        log.info(
            "llm.call_recorded",
            model=model,
            purpose=purpose,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read=cr,
            cost_usd=cost,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("llm.record_failed", error=str(e), purpose=purpose, model=model)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
async def complete(
    *,
    model: str,
    system: str | list[dict[str, Any]],
    user: str | list[dict[str, Any]],
    max_tokens: int = 2048,
    temperature: float = 0.4,
    cache_system: bool = True,
    user_id: UUID | None = None,
    purpose: str = "other",
) -> str:
    """Run a single message turn and return the assistant text.

    `system` and `user` may be plain strings or pre-built content blocks. When
    plain strings are supplied and `cache_system` is True, the system block is
    wrapped with `cache_control={"type": "ephemeral"}`.

    `user_id` + `purpose` are persisted with the usage stats for cost tracking.
    Pass them from each call site (scoring / generation / cv_parse / …).
    The Anthropic key is resolved from the user's DB-stored value first, then
    the global env var.
    """
    if isinstance(system, str):
        system_param = [
            {
                "type": "text",
                "text": system,
                **({"cache_control": {"type": "ephemeral"}} if cache_system else {}),
            }
        ]
    else:
        system_param = system

    if isinstance(user, str):
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    else:
        user_content = user

    client = _client(user_id=user_id)
    log.debug("llm.complete", model=model, purpose=purpose, max_tokens=max_tokens)
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_param,
        messages=[{"role": "user", "content": user_content}],
    )

    # Record usage — best-effort, never blocks the actual reply.
    if hasattr(resp, "usage"):
        _record_call(user_id=user_id, model=model, purpose=purpose, usage=resp.usage)

    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()
