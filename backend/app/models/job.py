"""Job model — global, deduped by (source_portal, external_id)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import JsonB as _JsonB


class Job(UUIDPKMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_portal", "external_id", name="uq_jobs_portal_external"),
    )

    source_portal: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    modality: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    description_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    application_type: Mapped[str | None] = mapped_column(String(50))
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(_JsonB)
