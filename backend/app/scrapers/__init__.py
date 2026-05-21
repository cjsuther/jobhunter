"""Job scrapers — one class per portal, all implement BaseJobScraper."""

from app.scrapers.base import BaseJobScraper
from app.scrapers.bumeran import BumeranScraper
from app.scrapers.clarin import ClarinScraper
from app.scrapers.computrabajo import ComputrabajoScraper
from app.scrapers.linkedin import LinkedInScraper
from app.scrapers.portal_empleo_ba import PortalEmpleoBAScraper
from app.scrapers.zonajobs import ZonaJobsScraper

PORTAL_SCRAPERS: dict[str, type[BaseJobScraper]] = {
    "bumeran": BumeranScraper,
    "zonajobs": ZonaJobsScraper,
    "computrabajo": ComputrabajoScraper,
    "linkedin": LinkedInScraper,
    "clarin": ClarinScraper,
    "portal_empleo_ba": PortalEmpleoBAScraper,
}

__all__ = ["BaseJobScraper", "PORTAL_SCRAPERS"]
