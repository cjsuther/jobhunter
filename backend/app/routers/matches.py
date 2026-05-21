"""Match routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.job import Job
from app.models.match import GeneratedMaterial, UserJobMatch
from app.models.profile import Profile
from app.models.user import User
from app.schemas.matches import (
    MaterialPublic,
    MatchDetail,
    MatchListItem,
    RejectMatchRequest,
    StatusUpdateRequest,
)

router = APIRouter()

ALLOWED_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "applied",
    "responded",
    "interview",
    "offer",
    "closed",
}


def _get_owned_match(db: Session, match_id: UUID, user: User) -> UserJobMatch:
    match = (
        db.query(UserJobMatch)
        .options(joinedload(UserJobMatch.materials))
        .filter(UserJobMatch.id == match_id)
        .one_or_none()
    )
    if not match:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    if match.user_id != user.id and not user.is_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    return match


def _to_list_item(match: UserJobMatch, job: Job, profile: Profile) -> dict:
    return {
        "id": match.id,
        "job": job,
        "profile_id": match.profile_id,
        "profile_name": profile.name,
        "fit_score": match.fit_score,
        "recommended_action": match.recommended_action,
        "strengths": match.strengths,
        "red_flags": match.red_flags,
        "status": match.status,
        "scored_at": match.scored_at,
    }


@router.get("", response_model=list[MatchListItem])
def list_matches(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    portal: str | None = None,
    profile_id: UUID | None = None,
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    q = (
        db.query(UserJobMatch, Job, Profile)
        .join(Job, UserJobMatch.job_id == Job.id)
        .join(Profile, UserJobMatch.profile_id == Profile.id)
        .filter(UserJobMatch.user_id == current.id)
        .filter(UserJobMatch.fit_score >= min_score)
    )
    if status_filter:
        q = q.filter(UserJobMatch.status == status_filter)
    if portal:
        q = q.filter(Job.source_portal == portal)
    if profile_id:
        q = q.filter(UserJobMatch.profile_id == profile_id)
    q = q.order_by(UserJobMatch.fit_score.desc(), UserJobMatch.scored_at.desc())
    rows = q.offset(offset).limit(limit).all()
    return [_to_list_item(m, j, p) for m, j, p in rows]


@router.get("/{match_id}", response_model=MatchDetail)
def get_match(
    match_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    match = _get_owned_match(db, match_id, current)
    job = db.get(Job, match.job_id)
    profile = db.get(Profile, match.profile_id)
    base = _to_list_item(match, job, profile)  # type: ignore[arg-type]
    base.update(
        {
            "scoring_reasoning": match.scoring_reasoning,
            "user_notes": match.user_notes,
            "materials": match.materials,
        }
    )
    return base


@router.post("/{match_id}/approve", response_model=MatchListItem)
def approve_match(
    match_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    match = _get_owned_match(db, match_id, current)
    match.status = "approved"
    db.commit()
    db.refresh(match)
    job = db.get(Job, match.job_id)
    profile = db.get(Profile, match.profile_id)
    return _to_list_item(match, job, profile)  # type: ignore[arg-type]


@router.post("/{match_id}/reject", response_model=MatchListItem)
def reject_match(
    match_id: UUID,
    payload: RejectMatchRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    match = _get_owned_match(db, match_id, current)
    match.status = "rejected"
    if payload.reason:
        match.user_notes = (match.user_notes or "") + f"\n[rejected]: {payload.reason}"
    db.commit()
    db.refresh(match)
    job = db.get(Job, match.job_id)
    profile = db.get(Profile, match.profile_id)
    return _to_list_item(match, job, profile)  # type: ignore[arg-type]


@router.post("/{match_id}/apply", status_code=status.HTTP_202_ACCEPTED)
def apply_match(
    match_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    """Enqueue the applier worker. In MVP this just marks the intent."""
    match = _get_owned_match(db, match_id, current)
    match.status = "approved"
    db.commit()
    from app.workers.apply_tasks import enqueue_apply

    enqueue_apply(match.id)
    return {"status": "queued", "match_id": str(match.id)}


@router.post("/{match_id}/mark-applied", response_model=MatchListItem)
def mark_applied_manual(
    match_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    from app.models.application import Application

    match = _get_owned_match(db, match_id, current)
    match.status = "applied"
    app_row = Application(match_id=match.id, channel="manual_external")
    db.add(app_row)
    db.commit()
    db.refresh(match)
    job = db.get(Job, match.job_id)
    profile = db.get(Profile, match.profile_id)
    return _to_list_item(match, job, profile)  # type: ignore[arg-type]


@router.post("/{match_id}/regenerate-cv", status_code=status.HTTP_202_ACCEPTED)
def regenerate_cv(
    match_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    match = _get_owned_match(db, match_id, current)
    from app.workers.generate_tasks import enqueue_generate_cv

    enqueue_generate_cv(match.id)
    return {"status": "queued", "type": "cv", "match_id": str(match.id)}


@router.post("/{match_id}/regenerate-letter", status_code=status.HTTP_202_ACCEPTED)
def regenerate_letter(
    match_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    match = _get_owned_match(db, match_id, current)
    from app.workers.generate_tasks import enqueue_generate_letter

    enqueue_generate_letter(match.id)
    return {"status": "queued", "type": "cover_letter", "match_id": str(match.id)}


class MaterialEditRequest(BaseModel):
    content_md: str


def _get_owned_material(
    db: Session, match_id: UUID, material_id: UUID, user: User
) -> GeneratedMaterial:
    match = _get_owned_match(db, match_id, user)
    material = db.get(GeneratedMaterial, material_id)
    if not material or material.match_id != match.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "material not found")
    return material


@router.put(
    "/{match_id}/materials/{material_id}",
    response_model=MaterialPublic,
)
def edit_material(
    match_id: UUID,
    material_id: UUID,
    payload: MaterialEditRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> GeneratedMaterial:
    """Replace the content of an existing material with user-edited markdown.

    Re-renders the PDF synchronously (WeasyPrint, < 2s). Does NOT bump version —
    a regenerate (LLM) is what creates new versions. Edits modify the current
    version in-place; if you want to keep the LLM version, regenerate first then
    edit.
    """
    material = _get_owned_material(db, match_id, material_id, current)

    new_md = payload.content_md.strip()
    if not new_md:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "content_md is empty")

    from app.services.pdf import markdown_to_pdf
    from app.services.storage import save_generated_pdf

    pdf_bytes = markdown_to_pdf(new_md)
    pdf_path = save_generated_pdf(
        current.id, material.match_id, kind=material.type, content=pdf_bytes
    )

    material.content_md = new_md
    material.pdf_path = pdf_path
    db.commit()
    db.refresh(material)
    return material


@router.get("/{match_id}/materials/{material_id}/download")
def download_material(
    match_id: UUID,
    material_id: UUID,
    fmt: str = Query(default="pdf", regex="^(pdf|docx|md)$"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Response:
    """Stream the material in the requested format.

    - `pdf`: re-render on the fly from current `content_md` (avoids stale PDFs).
    - `docx`: convert markdown to Word document.
    - `md`: raw markdown source.
    """
    material = _get_owned_material(db, match_id, material_id, current)
    job = db.get(Job, db.get(UserJobMatch, material.match_id).job_id)
    company = (job.company if job and job.company else "empresa").replace(" ", "-")[:40]
    kind = "cv" if material.type == "cv" else "carta"
    base_name = f"{kind}-{company}-v{material.version}"

    if fmt == "md":
        return Response(
            content=material.content_md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.md"'},
        )

    if fmt == "docx":
        from app.services.docx_render import markdown_to_docx

        data = markdown_to_docx(material.content_md)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.docx"'},
        )

    # pdf
    from app.services.pdf import markdown_to_pdf

    data = markdown_to_pdf(material.content_md)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{base_name}.pdf"'},
    )


@router.put("/{match_id}/status", response_model=MatchListItem)
def update_status(
    match_id: UUID,
    payload: StatusUpdateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid status: {payload.status}")
    match = _get_owned_match(db, match_id, current)
    match.status = payload.status
    if payload.notes:
        match.user_notes = (match.user_notes or "") + f"\n{payload.notes}"
    db.commit()
    db.refresh(match)
    job = db.get(Job, match.job_id)
    profile = db.get(Profile, match.profile_id)
    return _to_list_item(match, job, profile)  # type: ignore[arg-type]
