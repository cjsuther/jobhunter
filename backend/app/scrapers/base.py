"""Base scraper interface + shared schemas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapeCriteria:
    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    seniority_levels: list[str] = field(default_factory=list)
    max_results: int = 50


@dataclass
class RawJob:
    """Lightweight result returned by `search()` — full detail fetched later."""

    external_id: str
    external_url: str
    title: str
    company: str | None = None
    location: str | None = None
    posted_at: datetime | None = None


@dataclass
class JobDetail:
    external_id: str
    external_url: str
    title: str
    company: str | None
    location: str | None
    modality: str | None
    description: str | None
    posted_at: datetime | None
    application_type: str | None
    raw: dict | None = None


class BaseJobScraper(ABC):
    portal_name: str = "base"

    @abstractmethod
    async def search(self, criteria: ScrapeCriteria) -> list[RawJob]:
        """Return lightweight job listings matching the criteria."""

    @abstractmethod
    async def get_detail(self, external_id: str) -> JobDetail:
        """Return full job detail (description, etc.)."""
