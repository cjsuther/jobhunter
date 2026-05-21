"""Generation tasks — adapt CV and cover letter for a match."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.logging_setup import get_logger
from app.models.job import Job
from app.models.match import GeneratedMaterial, UserJobMatch
from app.models.profile import Profile
from app.services.generator import generate_cover_letter, generate_cv_markdown
from app.services.pdf import markdown_to_pdf
from app.services.storage import save_generated_pdf

log = get_logger("app.workers.generate")


def enqueue_generate_cv(match_id: UUID) -> None:
    generate_cv.delay(str(match_id))


def enqueue_generate_letter(match_id: UUID) -> None:
    generate_letter.delay(str(match_id))


def _load_match_context(db, match_id: str):
    match = db.get(UserJobMatch, UUID(match_id))
    if not match:
        return None
    job = db.get(Job, match.job_id)
    # The profile that scored this match — used for CV/letter adaptation.
    profile = db.get(Profile, match.profile_id)
    profile_dict = {
        "full_name": getattr(profile, "full_name", None),
        "headline": getattr(profile, "headline", None),
        "about_text": getattr(profile, "about_text", None),
        "cv_base_json": getattr(profile, "cv_base_json", {}) or {},
    }
    job_dict = {
        "title": job.title,
        "company": job.company,
        "description": job.description,
    }
    return match, job_dict, profile_dict


def _next_version(db, match_id: UUID, type_: str) -> int:
    last = (
        db.query(GeneratedMaterial)
        .filter(GeneratedMaterial.match_id == match_id, GeneratedMaterial.type == type_)
        .order_by(GeneratedMaterial.version.desc())
        .first()
    )
    return (last.version + 1) if last else 1


@celery_app.task(name="app.workers.generate_tasks.generate_materials")
def generate_materials(match_id: str) -> dict:
    """Convenience task — generates both CV and letter."""
    cv_res = generate_cv(match_id)
    letter_res = generate_letter(match_id)
    return {"cv": cv_res, "letter": letter_res}


@celery_app.task(name="app.workers.generate_tasks.generate_cv")
def generate_cv(match_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        ctx = _load_match_context(db, match_id)
        if ctx is None:
            return {"status": "missing"}
        match, job_dict, profile_dict = ctx
        md = asyncio.run(generate_cv_markdown(profile_dict, job_dict, user_id=match.user_id))
        pdf = markdown_to_pdf(md)
        path = save_generated_pdf(match.user_id, match.id, kind="cv", content=pdf)
        material = GeneratedMaterial(
            match_id=match.id,
            type="cv",
            content_md=md,
            pdf_path=path,
            version=_next_version(db, match.id, "cv"),
            model_used=settings.llm_model_generation,
        )
        db.add(material)
        db.commit()
        db.refresh(material)
        return {"status": "ok", "material_id": str(material.id)}
    finally:
        db.close()


@celery_app.task(name="app.workers.generate_tasks.generate_letter")
def generate_letter(match_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        ctx = _load_match_context(db, match_id)
        if ctx is None:
            return {"status": "missing"}
        match, job_dict, profile_dict = ctx
        md = asyncio.run(generate_cover_letter(profile_dict, job_dict, user_id=match.user_id))
        pdf = markdown_to_pdf(md)
        path = save_generated_pdf(match.user_id, match.id, kind="cover_letter", content=pdf)
        material = GeneratedMaterial(
            match_id=match.id,
            type="cover_letter",
            content_md=md,
            pdf_path=path,
            version=_next_version(db, match.id, "cover_letter"),
            model_used=settings.llm_model_generation,
        )
        db.add(material)
        db.commit()
        db.refresh(material)
        return {"status": "ok", "material_id": str(material.id)}
    finally:
        db.close()
