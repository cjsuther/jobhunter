"""Scraper debug endpoints — preview a portal scrape without persisting anything.

Useful when:
- Building/debugging a new scraper
- Diagnosing why "Correr ahora" returns 0 jobs (selectors stale? portal blocking us?)
- Sanity-checking criteria keywords before committing to a full scrape

Auth-required but not admin-only (read-only network egress, no DB writes).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.logging_setup import get_logger
from app.models.user import User
from app.scrapers import PORTAL_SCRAPERS
from app.scrapers.base import RawJob, ScrapeCriteria

router = APIRouter()
log = get_logger("app.routers.scrapers")


class RawJobOut(BaseModel):
    external_id: str
    external_url: str
    title: str
    company: str | None
    location: str | None
    posted_at: datetime | None


class PreviewResponse(BaseModel):
    portal: str
    keywords: list[str]
    locations: list[str]
    count: int
    jobs: list[RawJobOut]
    elapsed_seconds: float
    error: str | None = None


class PortalInfo(BaseModel):
    portal: str
    available: bool


@router.get("/portals", response_model=list[PortalInfo])
def list_supported_portals(
    _: User = Depends(get_current_user),
) -> list[PortalInfo]:
    return [PortalInfo(portal=p, available=True) for p in sorted(PORTAL_SCRAPERS.keys())]


def _raw_to_out(r: RawJob) -> RawJobOut:
    return RawJobOut(
        external_id=r.external_id,
        external_url=r.external_url,
        title=r.title,
        company=r.company,
        location=r.location,
        posted_at=r.posted_at,
    )


@router.get("/{portal}/preview", response_model=PreviewResponse)
async def preview_scrape(
    portal: str,
    keywords: Annotated[list[str], Query()] = [],
    locations: Annotated[list[str], Query()] = [],
    max_results: int = Query(default=10, ge=1, le=30),
    _: User = Depends(get_current_user),
) -> PreviewResponse:
    """Run the scraper's `search()` and return the first N results.

    Async on purpose — Playwright-based scrapers (Bumeran, ZonaJobs) need to
    share the event loop instead of spawning a fresh one with `asyncio.run`.

    Does NOT call `get_detail()` (avoids extra requests during a quick probe) and
    does NOT persist anything. Safe to hit repeatedly.
    """
    scraper_cls = PORTAL_SCRAPERS.get(portal)
    if scraper_cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown portal: {portal}")

    crit = ScrapeCriteria(
        keywords=[k for k in keywords if k],
        locations=[loc for loc in locations if loc],
        max_results=max_results,
    )

    t0 = time.monotonic()
    log.info(
        "scrapers.preview_start",
        portal=portal,
        keywords=crit.keywords,
        locations=crit.locations,
    )
    try:
        scraper = scraper_cls()
        raws: list[RawJob] = await scraper.search(crit)
    except Exception as e:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        log.exception(
            "scrapers.preview_failed",
            portal=portal,
            elapsed=elapsed,
            error=str(e),
        )
        return PreviewResponse(
            portal=portal,
            keywords=crit.keywords,
            locations=crit.locations,
            count=0,
            jobs=[],
            elapsed_seconds=round(elapsed, 2),
            error=f"{type(e).__name__}: {e}",
        )

    elapsed = time.monotonic() - t0
    log.info(
        "scrapers.preview_done",
        portal=portal,
        elapsed=elapsed,
        count=len(raws),
    )
    return PreviewResponse(
        portal=portal,
        keywords=crit.keywords,
        locations=crit.locations,
        count=len(raws),
        jobs=[_raw_to_out(r) for r in raws[:max_results]],
        elapsed_seconds=round(elapsed, 2),
    )
