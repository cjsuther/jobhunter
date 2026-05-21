"""Scraping Celery tasks — orchestrate portal scrapers, dedupe, persist, enqueue scoring."""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.celery_app import celery_app
from app.db import SessionLocal
from app.logging_setup import get_logger
from app.models.job import Job
from app.models.search_criteria import SearchCriteria
from app.models.user import User

if TYPE_CHECKING:
    from app.scrapers.base import BaseJobScraper, JobDetail, RawJob, ScrapeCriteria

log = get_logger("app.workers.scrape")


def enqueue_scrape_for_criteria(criteria_id: UUID) -> None:
    """Helper used by the criteria router and beat scheduler."""
    scrape_criteria.delay(str(criteria_id))


@celery_app.task(name="app.workers.scrape_tasks.scrape_all_active_criteria")
def scrape_all_active_criteria() -> int:
    """Beat task — enqueues one job per active criteria."""
    db = SessionLocal()
    try:
        rows = db.query(SearchCriteria).filter(SearchCriteria.active.is_(True)).all()
        for c in rows:
            scrape_criteria.delay(str(c.id))
        log.info("scrape.beat_dispatched", count=len(rows))
        return len(rows)
    finally:
        db.close()


def _build_scrape_criteria(crit: SearchCriteria) -> "ScrapeCriteria":
    from app.scrapers.base import ScrapeCriteria

    return ScrapeCriteria(
        keywords=list(crit.keywords or []),
        locations=list(crit.locations or []),
        modalities=list(crit.modalities or []),
        seniority_levels=list(crit.seniority_levels or []),
        max_results=50,
    )


def _description_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _scrape_portal(
    scraper: "BaseJobScraper",
    criteria: "ScrapeCriteria",
    fetch_detail: bool = True,
) -> list["JobDetail"]:
    """Run search then enrich with details. Returns ready-to-persist JobDetails."""
    raws = await scraper.search(criteria)
    log.info("scrape.search_done", portal=scraper.portal_name, count=len(raws))
    if not fetch_detail:
        # Convert RawJob → minimal JobDetail without description.
        from app.scrapers.base import JobDetail

        return [
            JobDetail(
                external_id=r.external_id,
                external_url=r.external_url,
                title=r.title,
                company=r.company,
                location=r.location,
                modality=None,
                description=None,
                posted_at=r.posted_at,
                application_type=None,
            )
            for r in raws
        ]

    details: list[JobDetail] = []  # type: ignore[no-redef]
    for raw in raws:
        try:
            detail = await scraper.get_detail(raw.external_id)
            # Backfill missing fields from listing data.
            if not detail.title:
                detail.title = raw.title
            if not detail.company:
                detail.company = raw.company
            if not detail.location:
                detail.location = raw.location
            if not detail.posted_at:
                detail.posted_at = raw.posted_at
            if not detail.external_url:
                detail.external_url = raw.external_url
            details.append(detail)
        except Exception as e:  # noqa: BLE001
            log.warning(
                "scrape.detail_failed",
                portal=scraper.portal_name,
                external_id=raw.external_id,
                error=str(e),
            )
            continue
    return details


def _keywords_match(job: Job, criteria_keywords: list[str]) -> bool:
    """Loose keyword filter — if no keywords, pass; else any keyword in title/desc."""
    if not criteria_keywords:
        return True
    haystack = " ".join(filter(None, [job.title, job.description or ""])).lower()
    return any(kw.lower() in haystack for kw in criteria_keywords)


def _matching_criteria(db, portal: str, job: Job) -> list[SearchCriteria]:
    """All active criteria (across profiles) that target this portal AND whose
    keywords loosely match the job. Used to enqueue scoring per profile.
    """
    rows = (
        db.query(SearchCriteria)
        .join(User, SearchCriteria.user_id == User.id)
        .filter(SearchCriteria.active.is_(True), User.is_active.is_(True))
        .all()
    )
    return [
        c
        for c in rows
        if portal in (c.portals_enabled or []) and _keywords_match(job, list(c.keywords or []))
    ]


def _persist_jobs(db, portal: str, details: list["JobDetail"]) -> list[Job]:
    """Insert new jobs, skip existing (unique by source_portal+external_id).
    Returns the list of NEWLY inserted Job rows.
    """
    new_jobs: list[Job] = []
    for d in details:
        try:
            job = Job(
                source_portal=portal,
                external_id=d.external_id,
                external_url=d.external_url,
                title=d.title or "(sin título)",
                company=d.company,
                location=d.location,
                modality=d.modality,
                description=d.description,
                description_hash=_description_hash(d.description),
                posted_at=d.posted_at,
                application_type=d.application_type,
                raw_json=d.raw,
            )
            db.add(job)
            db.flush()
            new_jobs.append(job)
        except IntegrityError:
            db.rollback()
            # Already scraped — ignore.
            continue
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.warning(
                "scrape.persist_failed",
                portal=portal,
                external_id=d.external_id,
                error=str(e),
            )
            continue
    db.commit()
    return new_jobs


@celery_app.task(name="app.workers.scrape_tasks.scrape_criteria")
def scrape_criteria(criteria_id: str) -> dict:
    """Run scrapers for all enabled portals on this criteria, then enqueue scoring
    for every (job, user) pair that matches the portal+keywords.
    """
    from app.scrapers import PORTAL_SCRAPERS
    from app.workers.score_tasks import score_job_for_criteria

    db = SessionLocal()
    try:
        crit = db.get(SearchCriteria, UUID(criteria_id))
        if not crit:
            log.warning("scrape.criteria_missing", criteria_id=criteria_id)
            return {"status": "missing"}

        scrape_criteria_obj = _build_scrape_criteria(crit)
        total_new = 0
        per_portal: dict[str, dict[str, int]] = {}

        for portal in crit.portals_enabled or []:
            scraper_cls = PORTAL_SCRAPERS.get(portal)
            if scraper_cls is None:
                log.warning("scrape.portal_unsupported", portal=portal)
                per_portal[portal] = {"found": 0, "new": 0, "error": 1}
                continue

            log.info("scrape.starting", portal=portal, criteria_id=criteria_id)
            try:
                details = asyncio.run(_scrape_portal(scraper_cls(), scrape_criteria_obj))
            except Exception as e:  # noqa: BLE001
                log.exception("scrape.portal_failed", portal=portal, error=str(e))
                per_portal[portal] = {"found": 0, "new": 0, "error": 1}
                continue

            new_jobs = _persist_jobs(db, portal, details)
            per_portal[portal] = {"found": len(details), "new": len(new_jobs), "error": 0}
            total_new += len(new_jobs)

            # Enqueue scoring for every (criteria) that should evaluate this job.
            # criteria.profile_id drives which profile's CV is used.
            for job in new_jobs:
                for c in _matching_criteria(db, portal, job):
                    score_job_for_criteria.delay(str(job.id), str(c.id))

        log.info(
            "scrape.criteria_done",
            criteria_id=criteria_id,
            total_new=total_new,
            per_portal=per_portal,
        )
        return {"status": "ok", "criteria_id": criteria_id, "per_portal": per_portal}
    finally:
        db.close()
