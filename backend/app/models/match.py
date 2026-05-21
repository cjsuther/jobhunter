"""User-Job match + generated materials."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import ArrayStr as _ArrayStr
from app.models._types import UuidType


class UserJobMatch(UUIDPKMixin, Base):
    __tablename__ = "user_job_matches"
    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_match_profile_job"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criteria_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidType(),
        ForeignKey("search_criteria.id", ondelete="SET NULL"),
    )
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_reasoning: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    red_flags: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    recommended_action: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    user_notes: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    materials: Mapped[list[GeneratedMaterial]] = relationship(
        "GeneratedMaterial", back_populates="match", cascade="all, delete-orphan"
    )


class GeneratedMaterial(UUIDPKMixin, Base):
    __tablename__ = "generated_materials"

    match_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("user_job_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    match: Mapped[UserJobMatch] = relationship("UserJobMatch", back_populates="materials")
