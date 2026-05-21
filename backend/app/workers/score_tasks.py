"""Scoring tasks — match a job against a profile using Haiku.

Each (profile, job) pair gets scored at most once. The same user can score
the same job multiple times if they have multiple profiles.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.celery_app import celery_app
from app.db import SessionLocal
from app.logging_setup import get_logger
from app.models.job import Job
from app.models.match import UserJobMatch
from app.models.profile import Profile
from app.models.search_criteria import SearchCriteria
from app.services.scoring import score_job

log = get_logger("app.workers.score")


def enqueue_score(job_id: UUID, criteria_id: UUID) -> None:
    """Enqueue scoring for a (job, criteria) pair. The profile is derived from
    `criteria.profile_id`.
    """
    score_job_for_criteria.delay(str(job_id), str(criteria_id))


@celery_app.task(
    name="app.workers.score_tasks.score_job_for_criteria", bind=True, max_retries=3
)
def score_job_for_criteria(self, job_id: str, criteria_id: str) -> dict:
    db = SessionLocal()
    try:
        criteria = db.get(SearchCriteria, UUID(criteria_id))
        if not criteria:
            return {"status": "missing_criteria"}
        job = db.get(Job, UUID(job_id))
        if not job:
            return {"status": "missing_job"}
        profile = db.get(Profile, criteria.profile_id)
        if not profile:
            return {"status": "missing_profile"}

        existing = (
            db.query(UserJobMatch)
            .filter(
                UserJobMatch.profile_id == profile.id,
                UserJobMatch.job_id == job.id,
            )
            .one_or_none()
        )
        if existing:
            return {"status": "already_scored", "match_id": str(existing.id)}

        profile_dict = {
            "full_name": profile.full_name,
            "headline": profile.headline,
            "current_location": profile.current_location,
            "years_experience": profile.years_experience,
            "about_text": profile.about_text,
            "preferred_titles": profile.preferred_titles,
            "excluded_companies": profile.excluded_companies,
            "excluded_keywords": profile.excluded_keywords,
            "cv_base_json": profile.cv_base_json or {},
        }
        criteria_dict = {
            "modalities": criteria.modalities,
            "salary_min_ars": criteria.salary_min_ars,
        }
        job_dict = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "modality": job.modality,
            "description": job.description,
        }

        try:
            result = asyncio.run(
                score_job(profile_dict, criteria_dict, job_dict, user_id=profile.user_id)
            )
        except Exception as e:  # noqa: BLE001
            log.exception("score.llm_error", error=str(e))
            raise self.retry(exc=e, countdown=10) from e

        match = UserJobMatch(
            user_id=profile.user_id,
            profile_id=profile.id,
            job_id=job.id,
            criteria_id=criteria.id,
            fit_score=int(result.get("fit_score", 0)),
            scoring_reasoning=result.get("reasoning"),
            strengths=result.get("strengths"),
            red_flags=result.get("red_flags"),
            recommended_action=result.get("recommended_action"),
            status="pending",
        )
        db.add(match)
        db.commit()
        db.refresh(match)

        # Materials are generated only on demand from the UI.
        return {"status": "scored", "match_id": str(match.id), "fit_score": match.fit_score}
    finally:
        db.close()
