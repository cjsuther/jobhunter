"""Search criteria — N per profile."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import ArrayStr as _ArrayStr
from app.models._types import UuidType

if TYPE_CHECKING:
    from app.models.profile import Profile


class SearchCriteria(UUIDPKMixin, Base):
    __tablename__ = "search_criteria"

    # Denormalised for fast "all of my criteria" queries; kept in sync with profile.user_id.
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
    name: Mapped[str | None] = mapped_column(String(100))
    keywords: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    locations: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    modalities: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    seniority_levels: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    salary_min_ars: Mapped[int | None] = mapped_column(BigInteger)
    contract_types: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    min_fit_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    daily_apply_cap: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    portals_enabled: Mapped[list[str]] = mapped_column(_ArrayStr, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    profile: Mapped[Profile] = relationship("Profile", back_populates="criteria")
