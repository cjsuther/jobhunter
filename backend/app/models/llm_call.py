"""Per-call record of every Anthropic API invocation — drives the cost dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import UuidType


class LLMCall(UUIDPKMixin, Base):
    __tablename__ = "llm_calls"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidType(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # Free-text tag for what triggered the call: scoring / cv_generation /
    # letter_generation / cv_parse / other.
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Computed at insert time using the pricing table — frozen so price changes
    # don't retroactively rewrite history.
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
