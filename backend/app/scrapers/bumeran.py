"""Bumeran scraper — JobInt platform, www.bumeran.com.ar."""

from app.scrapers._jobint import JobIntScraper
from app.scrapers.base import BaseJobScraper


class BumeranScraper(JobIntScraper, BaseJobScraper):
    portal_name = "bumeran"
    base_url = "https://www.bumeran.com.ar"
    log_name = "app.scrapers.bumeran"
