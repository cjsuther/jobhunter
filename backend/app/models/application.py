"""Application model — actual submission to a portal."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import UuidType


class Application(UUIDPKMixin, Base):
    __tablename__ = "applications"

    match_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("user_job_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str | None] = mapped_column(String(50))
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cv_material_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidType(),
        ForeignKey("generated_materials.id", ondelete="SET NULL"),
    )
    letter_material_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidType(),
        ForeignKey("generated_materials.id", ondelete="SET NULL"),
    )
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_type: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
