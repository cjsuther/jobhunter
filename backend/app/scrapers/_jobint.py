"""Shared scraper for JobInt portals (Bumeran, ZonaJobs).

Both sites are SPAs — the listing HTML is rendered client-side, so a plain
`httpx.get` returns an empty shell. We use Playwright to drive a headless
Chromium that executes the page JS, then parse the rendered DOM.

This is slower (~10–20s per search) but reliable. Each portal subclass only
overrides `base_url` and `portal_name`.
"""

from __future__ import annotations

import asyncio
import random
import re
from typing import Any
from urllib.parse import quote

from app.logging_setup import get_logger
from app.scrapers.base import JobDetail, RawJob, ScrapeCriteria

_UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _slug(s: str) -> str:
    s = re.sub(r"\s+", "-", s.strip().lower())
    return quote(s, safe="-")


class JobIntScraper:
    portal_name = "jobint"
    base_url = "https://www.bumeran.com.ar"
    log_name = "app.scrapers.jobint"

    # Selector wait — JobInt sites mount their results into one of these.
    _result_selectors = [
        "a[href*='/empleos/']",
        "div[id^='listado-']",
        "[class*='sc-'] a[href*='/empleos/']",
        "main a[href*='/empleos/']",
    ]

    def __init__(self, delay_range: tuple[float, float] = (1.5, 3.5)) -> None:
        self.delay_range = delay_range
        self.log = get_logger(self.log_name)

    def _search_url(self, keyword: str, location: str | None = None) -> str:
        if keyword and location:
            return f"{self.base_url}/empleos-busqueda-{_slug(keyword)}-en-{_slug(location)}.html"
        if keyword:
            return f"{self.base_url}/empleos-busqueda-{_slug(keyword)}.html"
        if location:
            return f"{self.base_url}/empleos-en-{_slug(location)}.html"
        return f"{self.base_url}/empleos.html"

    async def _fetch_rendered(self, url: str) -> str | None:
        """Open `url` in headless Chromium, wait for results to render, return HTML."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            self.log.error("scrape.playwright_missing", error=str(e))
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                ctx = await browser.new_context(
                    user_agent=random.choice(_UA_POOL),
                    locale="es-AR",
                    viewport={"width": 1366, "height": 900},
                )
                page = await ctx.new_page()
                # Block heavy resources to speed up.
                await page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in {"image", "media", "font"}
                    else route.continue_(),
                )
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                    # Wait for any of the result containers to appear.
                    for sel in self._result_selectors:
                        try:
                            await page.wait_for_selector(sel, timeout=6_000)
                            break
                        except Exception:  # noqa: BLE001
                            continue
                    # Let lazy renderers settle.
                    await asyncio.sleep(random.uniform(*self.delay_range))
                    html = await page.content()
                    return html
                finally:
                    await ctx.close()
                    await browser.close()
        except Exception as e:  # noqa: BLE001
            self.log.exception("scrape.playwright_failed", url=url, error=str(e))
            return None

    def _parse_listing(self, html: str) -> list[RawJob]:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        seen: set[str] = set()
        out: list[RawJob] = []

        # JobInt anchors look like: /empleos/<slug>-<id>.html
        anchors = tree.css("a[href*='/empleos/']")
        for a in anchors:
            href = a.attributes.get("href", "")
            if not href or "busqueda" in href or "empresa" in href:
                continue
            external_id = self._extract_external_id(href)
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)

            # Title — usually inside an h2/h3 child, fallback to the anchor text.
            title_node = a.css_first("h2") or a.css_first("h3") or a
            title = title_node.text(strip=True)
            if not title or len(title) > 300:
                continue

            # Walk up the DOM looking for siblings with company/location info.
            company: str | None = None
            location: str | None = None
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                # Try common JobInt class patterns
                if not company:
                    cn = parent.css_first("h3 + p, [class*='company'], [class*='Company']")
                    if cn:
                        company = cn.text(strip=True) or None
                if not location:
                    ln = parent.css_first("[class*='location'], [class*='Location']")
                    if ln:
                        location = ln.text(strip=True) or None
                if company and location:
                    break
                parent = parent.parent

            external_url = href if href.startswith("http") else f"{self.base_url}{href}"
            out.append(
                RawJob(
                    external_id=external_id,
                    external_url=external_url,
                    title=title,
                    company=company,
                    location=location,
                    posted_at=None,
                )
            )
        return out

    async def search(self, criteria: ScrapeCriteria) -> list[RawJob]:
        # JobInt's URL slug accepts a single search term cleanly. Run one fetch
        # per keyword × location combo (small N usually) and dedupe.
        keywords = criteria.keywords or [""]
        locations = criteria.locations or [""]
        urls = [self._search_url(k, loc or None) for k in keywords for loc in locations]

        seen: set[str] = set()
        out: list[RawJob] = []

        for url in urls:
            self.log.info("scrape.search", portal=self.portal_name, url=url)
            html = await self._fetch_rendered(url)
            if not html:
                self.log.warning("scrape.search_no_html", portal=self.portal_name, url=url)
                continue

            page_out = self._parse_listing(html)
            added = 0
            for r in page_out:
                if r.external_id in seen:
                    continue
                seen.add(r.external_id)
                out.append(r)
                added += 1
                if len(out) >= criteria.max_results:
                    break

            self.log.info(
                "scrape.search_page",
                portal=self.portal_name,
                url=url,
                found=len(page_out),
                new=added,
            )
            if len(out) >= criteria.max_results:
                break

        self.log.info(
            "scrape.search_done",
            portal=self.portal_name,
            total=len(out),
            queries=len(urls),
        )
        return out

    @staticmethod
    def _extract_external_id(href: str) -> str | None:
        # JobInt URLs typically end in -<digits>.html
        m = re.search(r"-(\d{6,})\.html", href)
        if m:
            return m.group(1)
        last = href.rstrip("/").split("/")[-1].replace(".html", "")
        return last or None

    async def get_detail(self, external_id: str) -> JobDetail:
        # We don't have the slug here; the listing already gives us a full URL,
        # so this fallback shape isn't always needed. JobInt usually redirects.
        url = f"{self.base_url}/empleos/{external_id}.html"
        html = await self._fetch_rendered(url)
        if not html:
            raise RuntimeError(f"detail fetch failed for {external_id}")

        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)

        def first(*selectors: str) -> Any:
            for sel in selectors:
                n = tree.css_first(sel)
                if n:
                    txt = n.text(strip=True)
                    if txt:
                        return txt
            return None

        title = first("h1", "h2[class*='title']", "[class*='title']") or ""
        company = first(
            "a[href*='/empresas/']",
            "[class*='company-name']",
            "[class*='companyName']",
            "h2 + p",
        )
        location = first("[class*='location']", "p[class*='location']")
        modality_raw = first(
            "[class*='modality']",
            "span:contains('Remoto')",
            "span:contains('Híbrido')",
            "span:contains('Presencial')",
        )
        modality = self._normalize_modality(modality_raw)

        desc_node = (
            tree.css_first("section[class*='description']")
            or tree.css_first("div[class*='description']")
            or tree.css_first("article[class*='detail']")
            or tree.css_first("[itemprop='description']")
        )
        description = desc_node.text(separator="\n", strip=True) if desc_node else None

        return JobDetail(
            external_id=external_id,
            external_url=url,
            title=title,
            company=company,
            location=location,
            modality=modality,
            description=description,
            posted_at=None,
            application_type="in_portal",
        )

    @staticmethod
    def _normalize_modality(raw: str | None) -> str | None:
        if not raw:
            return None
        r = raw.lower()
        if "remot" in r:
            return "remoto"
        if "híbr" in r or "hibr" in r:
            return "hibrido"
        if "presenc" in r:
            return "presencial"
        return None
