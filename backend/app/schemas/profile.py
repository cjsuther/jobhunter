"""Profile schemas — multi-profile per user."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, HttpUrl


class ProfileCreate(BaseModel):
    name: str
    full_name: str | None = None
    headline: str | None = None
    current_location: str | None = None
    years_experience: int | None = None
    linkedin_url: HttpUrl | None = None
    phone: str | None = None
    email_contact: EmailStr | None = None
    about_text: str | None = None
    preferred_titles: list[str] | None = None
    excluded_companies: list[str] | None = None
    excluded_keywords: list[str] | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    full_name: str | None = None
    headline: str | None = None
    current_location: str | None = None
    years_experience: int | None = None
    linkedin_url: HttpUrl | None = None
    phone: str | None = None
    email_contact: EmailStr | None = None
    about_text: str | None = None
    preferred_titles: list[str] | None = None
    excluded_companies: list[str] | None = None
    excluded_keywords: list[str] | None = None


class CVBaseUpdate(BaseModel):
    cv_base_json: dict[str, Any]


class ProfilePublic(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    full_name: str | None
    headline: str | None
    current_location: str | None
    years_experience: int | None
    linkedin_url: str | None
    phone: str | None
    email_contact: str | None
    cv_base_json: dict[str, Any]
    cv_base_pdf_path: str | None
    about_text: str | None
    preferred_titles: list[str] | None
    excluded_companies: list[str] | None
    excluded_keywords: list[str] | None

    model_config = {"from_attributes": True}


class ProfileSummary(BaseModel):
    """Light version for listings — no CV blob."""

    id: UUID
    name: str
    headline: str | None
    has_cv: bool

    model_config = {"from_attributes": True}


class CVParsedPreview(BaseModel):
    cv_base_json: dict[str, Any]
