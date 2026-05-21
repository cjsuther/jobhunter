"""Portal session model — encrypted cookies/creds per (user, portal)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import UuidType


class PortalSession(UUIDPKMixin, Base):
    __tablename__ = "portal_sessions"
    __table_args__ = (UniqueConstraint("user_id", "portal", name="uq_portal_session_user_portal"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    portal: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_cookies: Mapped[bytes | None] = mapped_column(LargeBinary)
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
