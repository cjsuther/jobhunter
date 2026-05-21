"""Tracking / funnel / metrics routes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.match import UserJobMatch
from app.models.user import User

router = APIRouter()


class FunnelResponse(BaseModel):
    scored: int
    above_threshold: int
    approved: int
    applied: int
    responded: int
    interview: int
    offer: int


class ApplicationListItem(BaseModel):
    id: UUID
    match_id: UUID
    job_title: str
    company: str | None
    portal: str
    channel: str | None
    applied_at: datetime
    response_type: str | None
    response_received_at: datetime | None
    current_status: str


class PortalStats(BaseModel):
    portal: str
    matches: int
    applied: int
    responded: int


@router.get("/funnel", response_model=FunnelResponse)
def funnel(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
) -> FunnelResponse:
    q = db.query(UserJobMatch).filter(UserJobMatch.user_id == current.id)
    if date_from:
        q = q.filter(UserJobMatch.scored_at >= date_from)
    if date_to:
        q = q.filter(UserJobMatch.scored_at <= date_to)

    scored = q.count()
    above = q.filter(UserJobMatch.fit_score >= 70).count()
    approved = q.filter(UserJobMatch.status.in_(["approved", "applied", "responded", "interview", "offer"])).count()
    applied = q.filter(UserJobMatch.status.in_(["applied", "responded", "interview", "offer"])).count()
    responded = q.filter(UserJobMatch.status.in_(["responded", "interview", "offer"])).count()
    interview = q.filter(UserJobMatch.status.in_(["interview", "offer"])).count()
    offer = q.filter(UserJobMatch.status == "offer").count()

    return FunnelResponse(
        scored=scored,
        above_threshold=above,
        approved=approved,
        applied=applied,
        responded=responded,
        interview=interview,
        offer=offer,
    )


@router.get("/applications", response_model=list[ApplicationListItem])
def list_applications(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[ApplicationListItem]:
    rows = (
        db.query(Application, UserJobMatch, Job)
        .join(UserJobMatch, Application.match_id == UserJobMatch.id)
        .join(Job, UserJobMatch.job_id == Job.id)
        .filter(UserJobMatch.user_id == current.id)
        .order_by(Application.applied_at.desc())
        .all()
    )
    return [
        ApplicationListItem(
            id=app.id,
            match_id=match.id,
            job_title=job.title,
            company=job.company,
            portal=job.source_portal,
            channel=app.channel,
            applied_at=app.applied_at,
            response_type=app.response_type,
            response_received_at=app.response_received_at,
            current_status=match.status,
        )
        for app, match, job in rows
    ]


@router.get("/by-portal", response_model=list[PortalStats])
def stats_by_portal(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[PortalStats]:
    out: dict[str, dict[str, int]] = {}
    rows = (
        db.query(Job.source_portal, UserJobMatch.status)
        .join(Job, UserJobMatch.job_id == Job.id)
        .filter(UserJobMatch.user_id == current.id)
        .all()
    )
    for portal, st in rows:
        d = out.setdefault(portal, {"matches": 0, "applied": 0, "responded": 0})
        d["matches"] += 1
        if st in ("applied", "responded", "interview", "offer"):
            d["applied"] += 1
        if st in ("responded", "interview", "offer"):
            d["responded"] += 1
    return [PortalStats(portal=p, **v) for p, v in out.items()]
