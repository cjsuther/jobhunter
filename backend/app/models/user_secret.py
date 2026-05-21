"""Per-user encrypted secrets — Anthropic API key for now."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import UuidType


class UserSecret(Base):
    __tablename__ = "user_secrets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Encrypted at rest with the global MASTER_ENCRYPTION_KEY (Fernet).
    anthropic_api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validated_ok: Mapped[bool | None] = mapped_column()
