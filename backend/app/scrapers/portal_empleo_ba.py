"""Portal Empleo BA (GCBA) scraper — Fase 2 stub."""

from app.scrapers.base import BaseJobScraper, JobDetail, RawJob, ScrapeCriteria


class PortalEmpleoBAScraper(BaseJobScraper):
    portal_name = "portal_empleo_ba"

    async def search(self, criteria: ScrapeCriteria) -> list[RawJob]:
        return []

    async def get_detail(self, external_id: str) -> JobDetail:
        return JobDetail(
            external_id=external_id,
            external_url=f"https://portalempleo.buenosaires.gob.ar/ofertas/{external_id}",
            title="",
            company=None,
            location=None,
            modality=None,
            description=None,
            posted_at=None,
            application_type="external_url",
        )
