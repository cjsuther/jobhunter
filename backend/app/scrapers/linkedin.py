"""LinkedIn scraper — guest mode.

This implementation uses LinkedIn's public `jobs-guest` search endpoint, which
returns server-rendered HTML fragments for unauthenticated requests. We do NOT
use logged-in cookies (Fase 2 in the spec) — that path is much riskier for
account bans.

Behavior:
- One request per (keyword, location) pair, paginated via `start` offset.
- Random User-Agent per request from a small pool.
- Hard delay of 3–8s between every request to stay well below LinkedIn's
  guest rate limit (~6/min). Spec §4.1.
- Description fetched from the public `jobs/view/{id}` page, which embeds a
  JSON-LD JobPosting block — robust against DOM changes.
- 0 results returned silently is normal: LinkedIn aggressively shows 429s and
  empty fragments to suspected scrapers. The worker logs the URL so you can
  open it in your own browser to compare.

Disclaimer: even guest scraping violates LinkedIn ToS technically. Use at
caps you're comfortable with and only for personal job hunting. Spec §7.6.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime
from urllib.parse import urlencode

import httpx
from selectolax.parser import HTMLParser, Node

from app.logging_setup import get_logger
from app.scrapers.base import BaseJobScraper, JobDetail, RawJob, ScrapeCriteria

log = get_logger("app.scrapers.linkedin")

_BASE = "https://www.linkedin.com"
_GUEST_SEARCH = f"{_BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"
_GUEST_DETAIL = f"{_BASE}/jobs-guest/jobs/api/jobPosting"  # /<id>

# Posted-time-range filter values LinkedIn accepts on `f_TPR`:
#   r86400  → last 24h
#   r604800 → last week
#   r2592000 → last month
_DEFAULT_TPR = "r604800"

# Workplace type filters on `f_WT`:
#   1 = on-site, 2 = remote, 3 = hybrid
_WT_MAP = {"presencial": "1", "remoto": "2", "hibrido": "3"}

_UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _delay_range() -> tuple[float, float]:
    return (3.0, 8.0)


def _job_id_from_url(url: str) -> str | None:
    # /jobs/view/<id>/?... or /jobs/view/<slug>-at-<company>-<id>/...
    m = re.search(r"/jobs/view/(?:[^/]*-)?(\d{6,})", url)
    if m:
        return m.group(1)
    m = re.search(r"currentJobId=(\d{6,})", url)
    if m:
        return m.group(1)
    return None


def _first(node: HTMLParser | Node | None, selectors: list[str]) -> Node | None:
    if node is None:
        return None
    for sel in selectors:
        n = node.css_first(sel)
        if n:
            return n
    return None


def _text(node: Node | None) -> str | None:
    if node is None:
        return None
    t = node.text(strip=True)
    return t or None


def _parse_iso_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class LinkedInScraper(BaseJobScraper):
    portal_name = "linkedin"

    def __init__(self, delay_range: tuple[float, float] | None = None) -> None:
        self.delay_range = delay_range or _delay_range()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(_UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        }

    def _search_url(
        self,
        keyword: str,
        location: str | None,
        modality: str | None,
        start: int,
    ) -> str:
        params: dict[str, str | int] = {
            "keywords": keyword,
            "start": start,
            "f_TPR": _DEFAULT_TPR,
        }
        if location:
            params["location"] = location
        if modality and modality in _WT_MAP:
            params["f_WT"] = _WT_MAP[modality]
        return f"{_GUEST_SEARCH}?{urlencode(params)}"

    async def _get(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            r = await client.get(url)
            await asyncio.sleep(random.uniform(*self.delay_range))
            if r.status_code == 429:
                log.warning("scrape.rate_limited", portal=self.portal_name, url=url)
                return None
            if r.status_code != 200:
                log.warning(
                    "scrape.http_error",
                    portal=self.portal_name,
                    url=url,
                    status=r.status_code,
                )
                return None
            return r.text
        except httpx.HTTPError as e:
            log.warning("scrape.http_failed", portal=self.portal_name, url=url, error=str(e))
            return None

    def _parse_search_html(self, html: str) -> list[RawJob]:
        tree = HTMLParser(html)
        out: list[RawJob] = []
        # Each card is wrapped in <li> or <div class="base-card">.
        cards = tree.css("li > div.base-card") or tree.css("div.base-card") or tree.css("li")
        for card in cards:
            link = _first(
                card,
                [
                    "a.base-card__full-link",
                    "a.base-search-card__title-link",
                    "a[href*='/jobs/view/']",
                ],
            )
            if not link:
                continue
            href = link.attributes.get("href", "")
            if not href:
                continue
            external_id = _job_id_from_url(href)
            if not external_id:
                continue

            title = _text(
                _first(
                    card,
                    ["h3.base-search-card__title", "h3.base-search-card__title span", "h3"],
                )
            )
            company = _text(
                _first(
                    card,
                    [
                        "h4.base-search-card__subtitle a",
                        "h4.base-search-card__subtitle",
                        ".base-search-card__subtitle",
                    ],
                )
            )
            location = _text(
                _first(card, [".job-search-card__location", ".job-result-card__location"])
            )

            posted_at: datetime | None = None
            time_node = card.css_first("time")
            if time_node:
                posted_at = _parse_iso_datetime(time_node.attributes.get("datetime"))

            # Strip tracking query params for cleanliness.
            external_url = href.split("?")[0]

            out.append(
                RawJob(
                    external_id=external_id,
                    external_url=external_url,
                    title=title or "(sin título)",
                    company=company,
                    location=location,
                    posted_at=posted_at,
                )
            )
        return out

    async def search(self, criteria: ScrapeCriteria) -> list[RawJob]:
        keywords = criteria.keywords or [""]
        locations = criteria.locations or [None]
        modalities = criteria.modalities or [None]

        seen: set[str] = set()
        out: list[RawJob] = []
        # Spec §4.1: cap max 50 results per search across all combos.
        cap = min(criteria.max_results, 50)

        async with httpx.AsyncClient(
            headers=self._headers(), timeout=20, follow_redirects=True
        ) as client:
            for keyword in keywords:
                for location in locations:
                    for modality in modalities:
                        if len(out) >= cap:
                            break
                        # Paginate up to 75 (3 pages of 25) per combo. Stop on first empty page.
                        for start in (0, 25, 50):
                            url = self._search_url(keyword, location, modality, start)
                            log.info("scrape.search", portal=self.portal_name, url=url)
                            html = await self._get(client, url)
                            if html is None or not html.strip():
                                break
                            page = self._parse_search_html(html)
                            added = 0
                            for r in page:
                                if r.external_id in seen:
                                    continue
                                seen.add(r.external_id)
                                out.append(r)
                                added += 1
                                if len(out) >= cap:
                                    break
                            log.info(
                                "scrape.search_page",
                                portal=self.portal_name,
                                url=url,
                                found=len(page),
                                new=added,
                            )
                            if added == 0 or len(out) >= cap:
                                break

        log.info(
            "scrape.search_done",
            portal=self.portal_name,
            total=len(out),
            keywords=keywords,
            locations=locations,
        )
        return out

    async def get_detail(self, external_id: str) -> JobDetail:
        url = f"{_BASE}/jobs/view/{external_id}/"
        async with httpx.AsyncClient(
            headers=self._headers(), timeout=20, follow_redirects=True
        ) as client:
            html = await self._get(client, url)
            if html is None:
                # Try the guest jobPosting API as a fallback — it returns just
                # the description fragment without the full page chrome.
                fallback = f"{_GUEST_DETAIL}/{external_id}"
                html = await self._get(client, fallback)
                if html is None:
                    raise RuntimeError(f"linkedin detail fetch failed for {external_id}")

        tree = HTMLParser(html)

        # Prefer the JSON-LD JobPosting block (most stable across DOM changes).
        title: str | None = None
        company: str | None = None
        location: str | None = None
        description: str | None = None
        posted_at: datetime | None = None
        raw_payload: dict = {}

        for ld_node in tree.css("script[type='application/ld+json']"):
            try:
                data = json.loads(ld_node.text())
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("@type") != "JobPosting":
                continue
            raw_payload = data
            title = data.get("title") or title
            hiring = data.get("hiringOrganization") or {}
            if isinstance(hiring, dict):
                company = hiring.get("name") or company
            loc = data.get("jobLocation") or {}
            if isinstance(loc, dict):
                addr = loc.get("address") or {}
                if isinstance(addr, dict):
                    bits = [addr.get("addressLocality"), addr.get("addressRegion")]
                    location = ", ".join(b for b in bits if b) or location
            description = data.get("description") or description
            posted_at = _parse_iso_datetime(data.get("datePosted")) or posted_at
            break

        # DOM fallbacks if JSON-LD missing.
        if not title:
            title = _text(_first(tree, ["h1", ".top-card-layout__title"])) or ""
        if not company:
            company = _text(
                _first(tree, [".topcard__org-name-link", ".topcard__flavor a", ".top-card-layout__entity-info a"])
            )
        if not location:
            location = _text(_first(tree, [".topcard__flavor--bullet", ".top-card-layout__entity-info"]))
        if not description:
            desc_node = _first(
                tree,
                [
                    ".show-more-less-html__markup",
                    ".description__text",
                    "section.description",
                ],
            )
            if desc_node:
                description = desc_node.text(separator="\n", strip=True)

        # Normalize HTML in description from JSON-LD (it comes with <br>, <p>, etc.).
        if description and ("<br" in description or "<p" in description):
            tmp = HTMLParser(f"<div>{description}</div>")
            div = tmp.css_first("div")
            if div is not None:
                description = div.text(separator="\n", strip=True)

        return JobDetail(
            external_id=external_id,
            external_url=url,
            title=title or "",
            company=company,
            location=location,
            modality=None,  # not exposed reliably in guest mode
            description=description,
            posted_at=posted_at,
            application_type="external_url",  # guest mode → opens LinkedIn page
            raw=raw_payload or None,
        )
