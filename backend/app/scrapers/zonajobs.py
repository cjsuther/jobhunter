"""ZonaJobs scraper — JobInt platform, www.zonajobs.com.ar (same structure as Bumeran)."""

from app.scrapers._jobint import JobIntScraper
from app.scrapers.base import BaseJobScraper


class ZonaJobsScraper(JobIntScraper, BaseJobScraper):
    portal_name = "zonajobs"
    base_url = "https://www.zonajobs.com.ar"
    log_name = "app.scrapers.zonajobs"
