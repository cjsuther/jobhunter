"""Cost dashboard endpoints — aggregate Anthropic API spend per user."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.llm_call import LLMCall
from app.models.user import User

router = APIRouter()


class BucketStats(BaseModel):
    cost_usd: float
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


class ModelBreakdown(BaseModel):
    model: str
    cost_usd: float
    calls: int


class PurposeBreakdown(BaseModel):
    purpose: str
    cost_usd: float
    calls: int


class CostSummary(BaseModel):
    today: BucketStats
    last_7_days: BucketStats
    last_30_days: BucketStats
    all_time: BucketStats
    by_model: list[ModelBreakdown]
    by_purpose: list[PurposeBreakdown]


def _now() -> datetime:
    return datetime.now(UTC)


def _start_of_today() -> datetime:
    n = _now()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket(db: Session, user_id, since: datetime | None) -> BucketStats:
    q = db.query(
        func.coalesce(func.sum(LLMCall.cost_usd), 0).label("cost_usd"),
        func.count(LLMCall.id).label("calls"),
        func.coalesce(func.sum(LLMCall.input_tokens), 0).label("input"),
        func.coalesce(func.sum(LLMCall.output_tokens), 0).label("output"),
        func.coalesce(func.sum(LLMCall.cache_read_input_tokens), 0).label("cache_read"),
    ).filter(LLMCall.user_id == user_id)
    if since:
        q = q.filter(LLMCall.created_at >= since)
    row = q.one()
    return BucketStats(
        cost_usd=float(row.cost_usd or 0),
        calls=int(row.calls or 0),
        input_tokens=int(row.input or 0),
        output_tokens=int(row.output or 0),
        cache_read_tokens=int(row.cache_read or 0),
    )


@router.get("/summary", response_model=CostSummary)
def cost_summary(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> CostSummary:
    today_start = _start_of_today()
    week_start = _now() - timedelta(days=7)
    month_start = _now() - timedelta(days=30)

    model_rows = (
        db.query(
            LLMCall.model,
            func.coalesce(func.sum(LLMCall.cost_usd), 0).label("cost_usd"),
            func.count(LLMCall.id).label("calls"),
        )
        .filter(LLMCall.user_id == current.id)
        .group_by(LLMCall.model)
        .all()
    )
    purpose_rows = (
        db.query(
            LLMCall.purpose,
            func.coalesce(func.sum(LLMCall.cost_usd), 0).label("cost_usd"),
            func.count(LLMCall.id).label("calls"),
        )
        .filter(LLMCall.user_id == current.id)
        .group_by(LLMCall.purpose)
        .all()
    )

    return CostSummary(
        today=_bucket(db, current.id, today_start),
        last_7_days=_bucket(db, current.id, week_start),
        last_30_days=_bucket(db, current.id, month_start),
        all_time=_bucket(db, current.id, since=None),
        by_model=[
            ModelBreakdown(
                model=r.model,
                cost_usd=float(r.cost_usd or 0),
                calls=int(r.calls or 0),
            )
            for r in model_rows
        ],
        by_purpose=[
            PurposeBreakdown(
                purpose=r.purpose,
                cost_usd=float(r.cost_usd or 0),
                calls=int(r.calls or 0),
            )
            for r in purpose_rows
        ],
    )
