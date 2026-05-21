"""Test fixtures.

Uses an in-process SQLite DB for speed. Multi-tenant tests still exercise the
auth dependency stack and FK constraints.
"""

from __future__ import annotations

import os
from collections.abc import Generator

# Set env BEFORE importing app modules so Settings picks them up.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-1234")
os.environ.setdefault("MASTER_ENCRYPTION_KEY", "HRxdKRRsMxwd5VlTicr53MtQvbcJinb5S2WQ60tSsPs=")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as app_db
from app.auth.passwords import hash_password
from app.db import Base
from app.main import app
from app.models.user import User


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestSession()
    # patch get_db dependency
    app_db.SessionLocal = TestSession  # type: ignore[assignment]
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        # Wipe data between tests (schema persists across the session-scoped engine).
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())


@pytest.fixture()
def client(db) -> TestClient:
    return TestClient(app)


def _make_user(db: Session, email: str, password: str = "secret123", role: str = "user") -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        full_name=email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def user_a(db) -> User:
    return _make_user(db, "a@example.com")


@pytest.fixture()
def user_b(db) -> User:
    return _make_user(db, "b@example.com")


@pytest.fixture()
def admin(db) -> User:
    return _make_user(db, "admin@example.com", role="admin")


def _login(client: TestClient, email: str, password: str = "secret123") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def auth_a(client, user_a) -> dict[str, str]:
    token = _login(client, user_a.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_b(client, user_b) -> dict[str, str]:
    token = _login(client, user_b.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_admin(client, admin) -> dict[str, str]:
    token = _login(client, admin.email)
    return {"Authorization": f"Bearer {token}"}
