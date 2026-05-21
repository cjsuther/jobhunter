"""Match / job schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobPublic(BaseModel):
    id: UUID
    source_portal: str
    external_id: str
    external_url: str
    title: str
    company: str | None
    location: str | None
    modality: str | None
    description: str | None
    posted_at: datetime | None
    scraped_at: datetime
    application_type: str | None

    model_config = {"from_attributes": True}


class MaterialPublic(BaseModel):
    id: UUID
    type: str
    content_md: str
    pdf_path: str | None
    version: int
    model_used: str | None
    generated_at: datetime

    model_config = {"from_attributes": True}


class MatchListItem(BaseModel):
    id: UUID
    job: JobPublic
    profile_id: UUID
    profile_name: str
    fit_score: int
    recommended_action: str | None
    strengths: list[str] | None
    red_flags: list[str] | None
    status: str
    scored_at: datetime

    model_config = {"from_attributes": True}


class MatchDetail(MatchListItem):
    scoring_reasoning: str | None
    user_notes: str | None
    materials: list[MaterialPublic]


class RejectMatchRequest(BaseModel):
    reason: str | None = None


class StatusUpdateRequest(BaseModel):
    status: str
    notes: str | None = None
