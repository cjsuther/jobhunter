"""Create an admin user from env vars or CLI args.

Reads BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD from settings (.env).
Idempotent: if the user already exists it just prints and exits 0.

Usage (inside the api container):
    python -m app.scripts.bootstrap_admin
    python -m app.scripts.bootstrap_admin --email foo@example.com --password secret
"""

from __future__ import annotations

import argparse
import sys

from app.auth.passwords import hash_password
from app.config import get_settings
from app.db import SessionLocal
from app.models.user import User


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=settings.bootstrap_admin_email)
    parser.add_argument("--password", default=settings.bootstrap_admin_password)
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args()

    if not args.email or not args.password:
        print("ERROR: provide --email/--password or set BOOTSTRAP_ADMIN_* in .env", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email.lower()).one_or_none()
        if existing:
            print(f"admin already exists: {existing.email} (id={existing.id})")
            return 0
        user = User(
            email=args.email.lower(),
            password_hash=hash_password(args.password),
            role="admin",
            is_active=True,
            full_name=args.name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"admin created: {user.email} (id={user.id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
