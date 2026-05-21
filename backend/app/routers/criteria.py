"""Search criteria routes — nested under profile.

Routes:
- GET    /api/v1/profiles/{profile_id}/criteria       — list
- POST   /api/v1/profiles/{profile_id}/criteria       — create
- GET    /api/v1/criteria                             — list across all of my profiles
- PUT    /api/v1/criteria/{criteria_id}               — update
- DELETE /api/v1/criteria/{criteria_id}               — delete
- POST   /api/v1/criteria/{criteria_id}/run           — enqueue scrape
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.profile import Profile
from app.models.search_criteria import SearchCriteria
from app.models.user import User
from app.schemas.criteria import CriteriaCreate, CriteriaPublic, CriteriaUpdate

# Two routers: one mounted under /profiles (nested create/list) and one under
# /criteria (flat list, update, delete, run).
profile_criteria_router = APIRouter()
router = APIRouter()


def _get_owned_profile(db: Session, profile_id: UUID, user: User) -> Profile:
    p = db.get(Profile, profile_id)
    if not p or (p.user_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return p


def _get_owned_criteria(db: Session, criteria_id: UUID, user: User) -> SearchCriteria:
    c = db.get(SearchCriteria, criteria_id)
    if not c or (c.user_id != user.id and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "criteria not found")
    return c


@profile_criteria_router.get(
    "/{profile_id}/criteria", response_model=list[CriteriaPublic]
)
def list_profile_criteria(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[SearchCriteria]:
    _get_owned_profile(db, profile_id, current)
    return (
        db.query(SearchCriteria)
        .filter(SearchCriteria.profile_id == profile_id)
        .order_by(SearchCriteria.created_at.desc())
        .all()
    )


@profile_criteria_router.post(
    "/{profile_id}/criteria",
    response_model=CriteriaPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_criteria(
    profile_id: UUID,
    payload: CriteriaCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> SearchCriteria:
    profile = _get_owned_profile(db, profile_id, current)
    c = SearchCriteria(
        user_id=profile.user_id,
        profile_id=profile.id,
        **payload.model_dump(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("", response_model=list[CriteriaPublic])
def list_all_criteria(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[SearchCriteria]:
    """All criteria across all of the user's profiles."""
    return (
        db.query(SearchCriteria)
        .filter(SearchCriteria.user_id == current.id)
        .order_by(SearchCriteria.created_at.desc())
        .all()
    )


@router.put("/{criteria_id}", response_model=CriteriaPublic)
def update_criteria(
    criteria_id: UUID,
    payload: CriteriaUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> SearchCriteria:
    c = _get_owned_criteria(db, criteria_id, current)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(c, key, value)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{criteria_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_criteria(
    criteria_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    c = _get_owned_criteria(db, criteria_id, current)
    db.delete(c)
    db.commit()


@router.post("/{criteria_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_criteria(
    criteria_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict[str, str]:
    c = _get_owned_criteria(db, criteria_id, current)
    from app.workers.scrape_tasks import enqueue_scrape_for_criteria

    enqueue_scrape_for_criteria(c.id)
    return {"status": "queued", "criteria_id": str(c.id)}
