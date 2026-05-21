"""Search criteria schemas."""

from uuid import UUID

from pydantic import BaseModel, Field


class CriteriaBase(BaseModel):
    name: str | None = None
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=list)
    seniority_levels: list[str] = Field(default_factory=list)
    salary_min_ars: int | None = None
    contract_types: list[str] = Field(default_factory=list)
    min_fit_score: int = 70
    daily_apply_cap: int = 10
    active: bool = True
    portals_enabled: list[str] = Field(default_factory=list)


class CriteriaCreate(CriteriaBase):
    pass


class CriteriaUpdate(BaseModel):
    name: str | None = None
    keywords: list[str] | None = None
    locations: list[str] | None = None
    modalities: list[str] | None = None
    seniority_levels: list[str] | None = None
    salary_min_ars: int | None = None
    contract_types: list[str] | None = None
    min_fit_score: int | None = None
    daily_apply_cap: int | None = None
    active: bool | None = None
    portals_enabled: list[str] | None = None


class CriteriaPublic(CriteriaBase):
    id: UUID
    user_id: UUID
    profile_id: UUID

    model_config = {"from_attributes": True}
