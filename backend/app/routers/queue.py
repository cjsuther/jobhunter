"""Queue inspection routes.

`/queue/status` returns Celery worker info + Redis queue depths — system-wide,
auth-required but not admin-only (it doesn't leak user data; only counts).

`/queue/activity` returns the current user's recent scrape/score/generate
activity, derived from DB timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.db import get_db
from app.logging_setup import get_logger
from app.models.job import Job
from app.models.match import GeneratedMaterial, UserJobMatch
from app.models.user import User

router = APIRouter()
log = get_logger("app.routers.queue")

# Redis list names per Celery queue. Must match the queues defined in celery_app.py.
_QUEUE_NAMES = ["default", "scrape", "scoring", "generation", "apply"]


class WorkerInfo(BaseModel):
    name: str
    status: str  # online | offline
    active: int  # tasks currently running
    reserved: int  # tasks prefetched, waiting locally
    queues: list[str]


class QueueDepth(BaseModel):
    name: str
    pending: int  # tasks waiting in Redis (not yet picked up)


class QueueStatus(BaseModel):
    workers: list[WorkerInfo]
    queues: list[QueueDepth]
    inspected_at: datetime


class RecentJob(BaseModel):
    id: UUID
    title: str
    company: str | None
    portal: str
    scraped_at: datetime


class RecentMatch(BaseModel):
    id: UUID
    job_title: str
    portal: str
    fit_score: int
    status: str
    scored_at: datetime


class RecentMaterial(BaseModel):
    id: UUID
    match_id: UUID
    type: str
    version: int
    generated_at: datetime


class ActivitySummary(BaseModel):
    jobs_last_24h: int
    matches_last_24h: int
    materials_last_24h: int
    recent_jobs: list[RecentJob]
    recent_matches: list[RecentMatch]
    recent_materials: list[RecentMaterial]


class ActiveTask(BaseModel):
    task_id: str
    name: str
    worker: str
    args: list[Any]
    elapsed_seconds: float | None  # since the worker started executing
    eta: str | None  # only set if Celery has it


class CancelResult(BaseModel):
    task_id: str
    revoked: bool
    terminated: bool
    message: str


def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.celery_broker_url, decode_responses=True)


def _inspect_workers() -> tuple[list[WorkerInfo], dict[str, Any]]:
    """Query running workers via Celery's control RPC.

    Returns (workers, raw_inspect_dict). Robust to no-workers-running.
    """
    try:
        from app.celery_app import celery_app

        i = celery_app.control.inspect(timeout=1.5)
        active = i.active() or {}
        reserved = i.reserved() or {}
        active_queues = i.active_queues() or {}
        stats = i.stats() or {}
    except Exception as e:  # noqa: BLE001
        log.warning("queue.inspect_failed", error=str(e))
        return [], {}

    workers: list[WorkerInfo] = []
    names = set(active) | set(reserved) | set(active_queues) | set(stats)
    for name in sorted(names):
        queues = [q.get("name", "?") for q in active_queues.get(name, [])]
        workers.append(
            WorkerInfo(
                name=name,
                status="online",
                active=len(active.get(name, [])),
                reserved=len(reserved.get(name, [])),
                queues=queues,
            )
        )
    return workers, {"active": active, "reserved": reserved}


@router.get("/status", response_model=QueueStatus)
def queue_status(_: User = Depends(get_current_user)) -> QueueStatus:
    workers, _raw = _inspect_workers()

    # Redis-side queue depths.
    depths: list[QueueDepth] = []
    try:
        r = _redis_client()
        for q in _QUEUE_NAMES:
            depths.append(QueueDepth(name=q, pending=r.llen(q)))
    except redis.RedisError as e:
        log.warning("queue.redis_unreachable", error=str(e))

    return QueueStatus(
        workers=workers,
        queues=depths,
        inspected_at=datetime.now(UTC),
    )


@router.get("/active", response_model=list[ActiveTask])
def list_active_tasks(_: User = Depends(get_current_user)) -> list[ActiveTask]:
    """Return all tasks currently executing across all workers."""
    try:
        from app.celery_app import celery_app

        active = celery_app.control.inspect(timeout=1.5).active() or {}
    except Exception as e:  # noqa: BLE001
        log.warning("queue.active_inspect_failed", error=str(e))
        return []

    now = datetime.now(UTC).timestamp()
    out: list[ActiveTask] = []
    for worker_name, tasks in active.items():
        for t in tasks or []:
            # Celery 'time_start' is a monotonic timestamp from the worker — not
            # comparable across hosts. We use it as a best-effort elapsed read.
            elapsed: float | None = None
            ts = t.get("time_start")
            if isinstance(ts, (int, float)):
                elapsed = max(0.0, now - float(ts))
            out.append(
                ActiveTask(
                    task_id=t.get("id", "?"),
                    name=t.get("name", "?"),
                    worker=worker_name,
                    args=t.get("args", []) or [],
                    elapsed_seconds=round(elapsed, 1) if elapsed is not None else None,
                    eta=t.get("eta"),
                )
            )
    # Most-recently-started first.
    out.sort(key=lambda x: x.elapsed_seconds or 0.0)
    return out


@router.post("/tasks/{task_id}/cancel", response_model=CancelResult)
def cancel_task(
    task_id: str,
    terminate: bool = True,
    signal_name: str = "SIGTERM",
    _: User = Depends(get_current_user),
) -> CancelResult:
    """Revoke a task. With `terminate=True` (default) the worker is signaled
    to kill the running process; useful for stuck Playwright sessions or long
    HTTP fetches that won't return on their own.
    """
    try:
        from app.celery_app import celery_app

        celery_app.control.revoke(task_id, terminate=terminate, signal=signal_name)
    except Exception as e:  # noqa: BLE001
        log.exception("queue.cancel_failed", task_id=task_id, error=str(e))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"could not revoke: {e}"
        ) from e

    log.info("queue.cancelled", task_id=task_id, terminate=terminate)
    return CancelResult(
        task_id=task_id,
        revoked=True,
        terminated=terminate,
        message=(
            "Tarea revocada y proceso terminado"
            if terminate
            else "Tarea marcada como revocada (terminará cuando llegue a un checkpoint)"
        ),
    )


@router.post("/queues/{queue_name}/purge", response_model=dict)
def purge_queue(
    queue_name: str, _: User = Depends(get_current_user)
) -> dict[str, Any]:
    """Discard all pending tasks in `queue_name` without affecting in-progress ones."""
    if queue_name not in _QUEUE_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown queue: {queue_name}")
    try:
        r = _redis_client()
        purged = r.delete(queue_name)
    except redis.RedisError as e:
        log.exception("queue.purge_failed", queue=queue_name, error=str(e))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e
    log.info("queue.purged", queue=queue_name, deleted_keys=purged)
    return {"queue": queue_name, "deleted_keys": purged}


@router.get("/activity", response_model=ActivitySummary)
def queue_activity(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> ActivitySummary:
    since = datetime.now(UTC) - timedelta(hours=24)

    # Recent jobs (scoped to the user via matches — `jobs` is a global table).
    job_rows = (
        db.query(Job)
        .join(UserJobMatch, UserJobMatch.job_id == Job.id)
        .filter(UserJobMatch.user_id == current.id)
        .order_by(Job.scraped_at.desc())
        .limit(20)
        .all()
    )
    jobs_24h = (
        db.query(Job)
        .join(UserJobMatch, UserJobMatch.job_id == Job.id)
        .filter(UserJobMatch.user_id == current.id, Job.scraped_at >= since)
        .count()
    )

    match_rows = (
        db.query(UserJobMatch, Job)
        .join(Job, UserJobMatch.job_id == Job.id)
        .filter(UserJobMatch.user_id == current.id)
        .order_by(UserJobMatch.scored_at.desc())
        .limit(20)
        .all()
    )
    matches_24h = (
        db.query(UserJobMatch)
        .filter(UserJobMatch.user_id == current.id, UserJobMatch.scored_at >= since)
        .count()
    )

    material_rows = (
        db.query(GeneratedMaterial)
        .join(UserJobMatch, GeneratedMaterial.match_id == UserJobMatch.id)
        .filter(UserJobMatch.user_id == current.id)
        .order_by(GeneratedMaterial.generated_at.desc())
        .limit(20)
        .all()
    )
    materials_24h = (
        db.query(GeneratedMaterial)
        .join(UserJobMatch, GeneratedMaterial.match_id == UserJobMatch.id)
        .filter(
            UserJobMatch.user_id == current.id,
            GeneratedMaterial.generated_at >= since,
        )
        .count()
    )

    return ActivitySummary(
        jobs_last_24h=jobs_24h,
        matches_last_24h=matches_24h,
        materials_last_24h=materials_24h,
        recent_jobs=[
            RecentJob(
                id=j.id,
                title=j.title,
                company=j.company,
                portal=j.source_portal,
                scraped_at=j.scraped_at,
            )
            for j in job_rows
        ],
        recent_matches=[
            RecentMatch(
                id=m.id,
                job_title=j.title,
                portal=j.source_portal,
                fit_score=m.fit_score,
                status=m.status,
                scored_at=m.scored_at,
            )
            for m, j in match_rows
        ],
        recent_materials=[
            RecentMaterial(
                id=mat.id,
                match_id=mat.match_id,
                type=mat.type,
                version=mat.version,
                generated_at=mat.generated_at,
            )
            for mat in material_rows
        ],
    )
