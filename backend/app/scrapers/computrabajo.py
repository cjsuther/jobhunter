"""Computrabajo (ar.computrabajo.com) — HTML scraper, no login required.

Search URL pattern:
  https://ar.computrabajo.com/trabajo-de-<slug>
  https://ar.computrabajo.com/empleos-en-<location-slug>?q=<query>

Listing card structure tends to change every few months. We try several common
selectors and skip the card gracefully if no link is found.
"""

from __future__ import annotations

import asyncio
import random
import re
from urllib.parse import quote_plus

import httpx
from selectolax.parser import HTMLParser, Node

from app.logging_setup import get_logger
from app.scrapers.base import BaseJobScraper, JobDetail, RawJob, ScrapeCriteria

log = get_logger("app.scrapers.computrabajo")

_BASE = "https://ar.computrabajo.com"
_UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _slugify(s: str) -> str:
    """Computrabajo URL slug: lowercase, spaces → hyphens, strip diacritics."""
    import unicodedata

    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    return re.sub(r"[\s_]+", "-", s)


def _first_text(node: Node | None) -> str | None:
    if node is None:
        return None
    txt = node.text(strip=True)
    return txt or None


def _try_selectors(root: Node | HTMLParser, selectors: list[str]) -> Node | None:
    for sel in selectors:
        n = root.css_first(sel)
        if n:
            return n
    return None


class ComputrabajoScraper(BaseJobScraper):
    portal_name = "computrabajo"

    def __init__(self, delay_range: tuple[float, float] = (1.5, 3.5)) -> None:
        self.delay_range = delay_range

    async def _get(self, url: str, client: httpx.AsyncClient | None = None) -> str:
        headers = {
            "User-Agent": random.choice(_UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        }
        own_client = client is None
        if client is None:
            client = httpx.AsyncClient(headers=headers, timeout=20, follow_redirects=True)
        try:
            r = await client.get(url)
            r.raise_for_status()
            await asyncio.sleep(random.uniform(*self.delay_range))
            return r.text
        finally:
            if own_client:
                await client.aclose()

    def _build_search_url(self, keyword: str, location: str) -> str:
        keyword_slug = _slugify(keyword) if keyword else ""
        location_slug = _slugify(location) if location else ""

        if keyword_slug and location_slug:
            return f"{_BASE}/trabajo-de-{keyword_slug}-en-{location_slug}"
        if keyword_slug:
            return f"{_BASE}/trabajo-de-{keyword_slug}"
        if location_slug:
            return f"{_BASE}/empleos-en-{location_slug}"
        # Fallback: free-text query parameter on home search
        return f"{_BASE}/ofertas-de-trabajo/?q={quote_plus(keyword)}"

    async def search(self, criteria: ScrapeCriteria) -> list[RawJob]:
        # Computrabajo treats the URL slug as a single search phrase. To match
        # multiple keywords we run one fetch per (keyword × location) and merge.
        keywords = criteria.keywords or [""]
        locations = criteria.locations or [""]
        urls = [
            self._build_search_url(k, loc) for k in keywords for loc in locations
        ]

        seen_ids: set[str] = set()
        out: list[RawJob] = []
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={
                "User-Agent": random.choice(_UA_POOL),
                "Accept-Language": "es-AR,es;q=0.9",
            },
        ) as client:
            for url in urls:
                log.info("scrape.search", portal=self.portal_name, url=url)
                try:
                    html = await self._get(url, client=client)
                except httpx.HTTPError as e:
                    log.warning(
                        "scrape.search_failed",
                        portal=self.portal_name,
                        url=url,
                        error=str(e),
                    )
                    continue

                page_out = self._parse_listing(html)
                added = 0
                for r in page_out:
                    if r.external_id in seen_ids:
                        continue
                    seen_ids.add(r.external_id)
                    out.append(r)
                    added += 1
                    if len(out) >= criteria.max_results:
                        break
                log.info(
                    "scrape.search_page",
                    portal=self.portal_name,
                    url=url,
                    found=len(page_out),
                    new=added,
                )
                if len(out) >= criteria.max_results:
                    break

        log.info(
            "scrape.search_done",
            portal=self.portal_name,
            total=len(out),
            queries=len(urls),
        )
        return out

    def _parse_listing(self, html: str) -> list[RawJob]:
        tree = HTMLParser(html)
        cards = tree.css("article.box_offer") or tree.css("article[data-id]") or tree.css(
            "div.iO[data-id]"
        )

        out: list[RawJob] = []
        for card in cards:
            link_node = _try_selectors(
                card,
                [
                    "a.js-o-link",
                    "h1.fs18 a",
                    "h2.fs18 a",
                    "h1 a[href*='/ofertas-de-trabajo/']",
                    "h2 a[href*='/ofertas-de-trabajo/']",
                    "a[href*='/ofertas-de-trabajo/']",
                ],
            )
            title_node = _try_selectors(card, ["h1 a", "h2 a", "h1", "h2"])
            company_node = _try_selectors(
                card,
                [
                    "p.dFlex a[href*='/empresa-']",
                    "p.fc_base a",
                    "p.fc_base",
                    "a.fc_base",
                    "span.fc_base",
                ],
            )
            location_node = _try_selectors(card, ["p.fc_aux", "span.fc_aux"])
            posted_node = _try_selectors(card, ["p.fs13.fc_aux", "p.fs13", "span.fs13"])

            if not link_node:
                continue
            href = link_node.attributes.get("href", "")
            if not href:
                continue
            external_url = href if href.startswith("http") else f"{_BASE}{href}"
            external_id = self._extract_external_id(href)
            if not external_id:
                continue

            out.append(
                RawJob(
                    external_id=external_id,
                    external_url=external_url,
                    title=_first_text(title_node) or _first_text(link_node) or "",
                    company=_first_text(company_node),
                    location=_first_text(location_node),
                    posted_at=None,  # 'hace N días' — could parse but low value
                )
            )

        return out

    @staticmethod
    def _extract_external_id(href: str) -> str | None:
        # Examples:
        #  /ofertas-de-trabajo/oferta-de-trabajo-de-...-EAB123ABC.html → EAB123ABC
        #  /ofertas-de-trabajo/?oferta=ABC123                          → ABC123
        m = re.search(r"-([A-Z0-9]{8,})\.html", href)
        if m:
            return m.group(1)
        m = re.search(r"oferta=([A-Za-z0-9]+)", href)
        if m:
            return m.group(1)
        # Fallback: last path segment without extension
        last = href.rstrip("/").split("/")[-1]
        last = last.split("?")[0].replace(".html", "")
        return last or None

    async def get_detail(self, external_id: str) -> JobDetail:
        # When called standalone we don't have the slug; we attempt two URL shapes.
        candidate_urls = [
            f"{_BASE}/ofertas-de-trabajo/?oferta={external_id}",
            f"{_BASE}/ofertas-de-trabajo/oferta-de-trabajo-{external_id}.html",
        ]
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": random.choice(_UA_POOL), "Accept-Language": "es-AR,es;q=0.9"},
        ) as client:
            html = None
            final_url = ""
            for url in candidate_urls:
                try:
                    r = await client.get(url)
                    if r.status_code == 200 and len(r.text) > 1000:
                        html = r.text
                        final_url = str(r.url)
                        break
                except httpx.HTTPError:
                    continue
            if html is None:
                raise RuntimeError(f"Could not fetch detail for {external_id}")

            await asyncio.sleep(random.uniform(*self.delay_range))

        tree = HTMLParser(html)
        title = _first_text(_try_selectors(tree, ["h1", "h2"])) or ""
        company = _first_text(
            _try_selectors(tree, ["a[href*='/empresa-']", "p.fc_base a", "p.fc_base"])
        )
        location = _first_text(_try_selectors(tree, ["p.fc_aux", "span.fc_aux"]))

        # Description: Computrabajo typically wraps the JD in #requisitos / div.fpb
        desc_node = _try_selectors(
            tree,
            [
                "div.fpb",
                "div.bWord",
                "section.fpb",
                "div[itemprop='description']",
                "div.disc",
            ],
        )
        description = None
        if desc_node:
            # Preserve line breaks for readability.
            description = desc_node.text(separator="\n", strip=True)

        return JobDetail(
            external_id=external_id,
            external_url=final_url,
            title=title,
            company=company,
            location=location,
            modality=None,  # Computrabajo rarely tags modality explicitly
            description=description,
            posted_at=None,
            application_type="external_url",
        )
