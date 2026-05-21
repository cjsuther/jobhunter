"""Portable column types — Postgres-native in prod, generic in tests (SQLite)."""

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator


class UuidType(TypeDecorator):
    """UUID column — native PG UUID, fallback to CHAR(36) on other backends."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        return str(value) if dialect.name != "postgresql" else value

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        import uuid

        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


ArrayStr = ARRAY(String).with_variant(JSON, "sqlite")
JsonB = JSONB().with_variant(JSON, "sqlite")
