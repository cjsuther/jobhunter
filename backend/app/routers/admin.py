"""Admin routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.match import UserJobMatch
from app.models.user import User
from app.schemas.auth import UserPublic

router = APIRouter()


class UserAdminUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = None


class AdminStats(BaseModel):
    users_total: int
    users_active: int
    jobs_total: int
    matches_total: int
    applications_total: int


@router.get("/users", response_model=list[UserPublic])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


@router.put("/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: UUID,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role is not None:
        if payload.role not in {"user", "admin"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid role")
        user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.get("/stats", response_model=AdminStats)
def admin_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminStats:
    return AdminStats(
        users_total=db.query(func.count(User.id)).scalar() or 0,
        users_active=db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0,
        jobs_total=db.query(func.count(Job.id)).scalar() or 0,
        matches_total=db.query(func.count(UserJobMatch.id)).scalar() or 0,
        applications_total=db.query(func.count(Application.id)).scalar() or 0,
    )
