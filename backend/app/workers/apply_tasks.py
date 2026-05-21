"""Apply tasks — Fase 1 only stages 'approved' matches; no scripted apply yet."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from app.celery_app import celery_app
from app.db import SessionLocal
from app.logging_setup import get_logger
from app.models.application import Application
from app.models.job import Job
from app.models.match import UserJobMatch

log = get_logger("app.workers.apply")

DAILY_CAPS_DEFAULT = {
    "linkedin": 15,
    "bumeran": 25,
    "zonajobs": 25,
    "computrabajo": 25,
    "clarin": 25,
    "portal_empleo_ba": 25,
}


def enqueue_apply(match_id: UUID) -> None:
    apply_match.delay(str(match_id))


def _count_today(db, user_id: UUID, portal: str) -> int:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    return (
        db.query(Application)
        .join(UserJobMatch, Application.match_id == UserJobMatch.id)
        .join(Job, UserJobMatch.job_id == Job.id)
        .filter(
            UserJobMatch.user_id == user_id,
            Job.source_portal == portal,
            Application.applied_at >= start,
        )
        .count()
    )


@celery_app.task(name="app.workers.apply_tasks.apply_match")
def apply_match(match_id: str) -> dict:
    """In Fase 1 (assisted mode) this only validates caps and leaves the match
    `approved`. The user opens the external URL and confirms manually.

    In Fase 3 (scripted mode) this dispatches to portal-specific Playwright
    appliers — see app/appliers/.
    """
    db = SessionLocal()
    try:
        match = db.get(UserJobMatch, UUID(match_id))
        if not match:
            return {"status": "missing"}
        job = db.get(Job, match.job_id)
        if not job:
            return {"status": "missing"}
        cap = DAILY_CAPS_DEFAULT.get(job.source_portal, 20)
        if _count_today(db, match.user_id, job.source_portal) >= cap:
            match.status = "queued_for_tomorrow"
            db.commit()
            log.info("apply.cap_reached", portal=job.source_portal, user_id=str(match.user_id))
            return {"status": "cap_reached"}

        # Fase 1 = assisted: nothing else to do here; user completes in portal.
        log.info("apply.staged", match_id=match_id, portal=job.source_portal)
        return {"status": "staged"}
    finally:
        db.close()
