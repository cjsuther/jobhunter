"""Profile CRUD — multiple profiles per user. Each profile has its own CV base."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.profile import Profile
from app.models.user import User
from app.schemas.profile import (
    CVBaseUpdate,
    CVParsedPreview,
    ProfileCreate,
    ProfilePublic,
    ProfileSummary,
    ProfileUpdate,
)

router = APIRouter()


def _get_owned_profile(db: Session, profile_id: UUID, user: User) -> Profile:
    p = db.get(Profile, profile_id)
    if not p or (p.user_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return p


def _to_summary(p: Profile) -> ProfileSummary:
    return ProfileSummary(
        id=p.id,
        name=p.name,
        headline=p.headline,
        has_cv=bool(p.cv_base_json),
    )


@router.get("", response_model=list[ProfileSummary])
def list_profiles(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[ProfileSummary]:
    rows = (
        db.query(Profile)
        .filter(Profile.user_id == current.id)
        .order_by(Profile.name.asc())
        .all()
    )
    return [_to_summary(p) for p in rows]


@router.post("", response_model=ProfilePublic, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Profile:
    data = payload.model_dump()
    if data.get("linkedin_url") is not None:
        data["linkedin_url"] = str(data["linkedin_url"])
    p = Profile(user_id=current.id, cv_base_json={}, **data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{profile_id}", response_model=ProfilePublic)
def get_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Profile:
    return _get_owned_profile(db, profile_id, current)


@router.put("/{profile_id}", response_model=ProfilePublic)
def update_profile(
    profile_id: UUID,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Profile:
    p = _get_owned_profile(db, profile_id, current)
    data = payload.model_dump(exclude_unset=True)
    if "linkedin_url" in data and data["linkedin_url"] is not None:
        data["linkedin_url"] = str(data["linkedin_url"])
    for key, value in data.items():
        setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    p = _get_owned_profile(db, profile_id, current)
    # Refuse to delete the only profile — that would orphan matches/criteria.
    count = db.query(Profile).filter(Profile.user_id == current.id).count()
    if count <= 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "no podés borrar tu único perfil"
        )
    db.delete(p)
    db.commit()


# ---- CV base per profile ---------------------------------------------------


@router.post(
    "/{profile_id}/cv",
    response_model=CVParsedPreview,
    status_code=status.HTTP_200_OK,
)
async def parse_cv_upload(
    profile_id: UUID,
    file: UploadFile,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> CVParsedPreview:
    p = _get_owned_profile(db, profile_id, current)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expected a PDF file")
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")

    from app.services.cv_parser import parse_cv_pdf
    from app.services.storage import save_cv_pdf

    pdf_path = save_cv_pdf(user_id=current.id, content=content, filename=file.filename)
    parsed = await parse_cv_pdf(content, user_id=current.id)
    p.cv_base_pdf_path = pdf_path
    db.commit()
    return CVParsedPreview(cv_base_json=parsed)


@router.put("/{profile_id}/cv", response_model=ProfilePublic)
def save_cv_base(
    profile_id: UUID,
    payload: CVBaseUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Profile:
    p = _get_owned_profile(db, profile_id, current)
    p.cv_base_json = payload.cv_base_json
    db.commit()
    db.refresh(p)
    return p


@router.get("/{profile_id}/cv/download")
def download_cv(
    profile_id: UUID,
    fmt: str = Query(default="pdf", regex="^(pdf|json|docx)$"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Response:
    p = _get_owned_profile(db, profile_id, current)
    base_name = f"cv-{p.name.replace(' ', '-')}"

    if fmt == "json":
        payload = p.cv_base_json or {}
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.json"'},
        )
    if fmt == "pdf":
        if not p.cv_base_pdf_path:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "este perfil no tiene PDF cargado"
            )
        from app.services.storage import read_object_bytes

        data = read_object_bytes(p.cv_base_pdf_path)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.pdf"'},
        )

    if not p.cv_base_json:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "este perfil no tiene CV JSON guardado"
        )
    from app.routers._cv_render import cv_json_to_markdown
    from app.services.docx_render import markdown_to_docx

    data = markdown_to_docx(cv_json_to_markdown(p.cv_base_json))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{base_name}.docx"'},
    )
