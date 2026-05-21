"""Profile model — N per user. Each profile has its own CV base + criteria."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._mixins import UUIDPKMixin
from app.models._types import ArrayStr as _ArrayStr
from app.models._types import JsonB as _JsonB
from app.models._types import UuidType

if TYPE_CHECKING:
    from app.models.search_criteria import SearchCriteria
    from app.models.user import User


class Profile(UUIDPKMixin, Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UuidType(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Perfil")
    full_name: Mapped[str | None] = mapped_column(String(255))
    headline: Mapped[str | None] = mapped_column(String(500))
    current_location: Mapped[str | None] = mapped_column(String(255))
    years_experience: Mapped[int | None] = mapped_column(Integer)
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(50))
    email_contact: Mapped[str | None] = mapped_column(String(255))
    cv_base_json: Mapped[dict[str, Any]] = mapped_column(_JsonB, nullable=False, default=dict)
    cv_base_pdf_path: Mapped[str | None] = mapped_column(String(500))
    about_text: Mapped[str | None] = mapped_column(Text)
    preferred_titles: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    excluded_companies: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    excluded_keywords: Mapped[list[str] | None] = mapped_column(_ArrayStr)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="profiles")
    criteria: Mapped[list[SearchCriteria]] = relationship(
        "SearchCriteria", back_populates="profile", cascade="all, delete-orphan"
    )
