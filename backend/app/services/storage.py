"""MinIO/S3 storage helpers."""

from __future__ import annotations

import io
from uuid import UUID, uuid4

from minio import Minio

from app.config import get_settings
from app.logging_setup import get_logger

log = get_logger("app.services.storage")


def _client() -> Minio:
    s = get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_use_ssl,
    )


def ensure_bucket() -> None:
    s = get_settings()
    c = _client()
    if not c.bucket_exists(s.minio_bucket):
        c.make_bucket(s.minio_bucket)
        log.info("storage.bucket_created", bucket=s.minio_bucket)


def _user_prefix(user_id: UUID) -> str:
    return f"users/{user_id}"


def save_cv_pdf(user_id: UUID, content: bytes, filename: str) -> str:
    ensure_bucket()
    s = get_settings()
    object_name = f"{_user_prefix(user_id)}/cv-base/{uuid4().hex}-{filename}"
    _client().put_object(
        s.minio_bucket,
        object_name,
        io.BytesIO(content),
        length=len(content),
        content_type="application/pdf",
    )
    return object_name


def save_generated_pdf(user_id: UUID, match_id: UUID, kind: str, content: bytes) -> str:
    ensure_bucket()
    s = get_settings()
    object_name = f"{_user_prefix(user_id)}/matches/{match_id}/{kind}-{uuid4().hex}.pdf"
    _client().put_object(
        s.minio_bucket,
        object_name,
        io.BytesIO(content),
        length=len(content),
        content_type="application/pdf",
    )
    return object_name


def presigned_url(object_name: str, expires_seconds: int = 3600) -> str:
    from datetime import timedelta

    s = get_settings()
    return _client().presigned_get_object(
        s.minio_bucket, object_name, expires=timedelta(seconds=expires_seconds)
    )


def read_object_bytes(object_name: str) -> bytes:
    """Fetch the full content of an object from MinIO."""
    s = get_settings()
    response = _client().get_object(s.minio_bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
