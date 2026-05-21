"""Clarín Empleos scraper — Fase 2 stub."""

from app.scrapers.base import BaseJobScraper, JobDetail, RawJob, ScrapeCriteria


class ClarinScraper(BaseJobScraper):
    portal_name = "clarin"

    async def search(self, criteria: ScrapeCriteria) -> list[RawJob]:
        return []

    async def get_detail(self, external_id: str) -> JobDetail:
        return JobDetail(
            external_id=external_id,
            external_url=f"https://www.clarin.com/empleos/{external_id}",
            title="",
            company=None,
            location=None,
            modality=None,
            description=None,
            posted_at=None,
            application_type="external_url",
        )
