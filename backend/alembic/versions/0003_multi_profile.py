"""Multi-profile: many profiles per user, many criteria per profile.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21

Idempotent — safe to re-run if a previous attempt failed mid-way. Every step
checks current schema state before applying.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return bool(row)


def _constraint_exists(conn, table: str, name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :n"
        ),
        {"t": table, "n": name},
    ).scalar()
    return bool(row)


def _index_exists(conn, name: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": name},
    ).scalar()
    return bool(row)


def _is_nullable(conn, table: str, column: str) -> bool:
    val = conn.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return val == "YES"


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. profiles: add id, name (skip if already added) ---------------
    if not _column_exists(conn, "profiles", "id"):
        op.execute("ALTER TABLE profiles ADD COLUMN id UUID")
    if not _column_exists(conn, "profiles", "name"):
        op.execute("ALTER TABLE profiles ADD COLUMN name VARCHAR(100)")

    # Backfill id + default name for any null rows.
    conn.execute(
        text(
            "UPDATE profiles "
            "SET id = COALESCE(id, uuid_generate_v4()), "
            "    name = COALESCE(name, 'Perfil principal')"
        )
    )

    # Set NOT NULL only if not already set.
    if _is_nullable(conn, "profiles", "id"):
        op.execute("ALTER TABLE profiles ALTER COLUMN id SET NOT NULL")
    if _is_nullable(conn, "profiles", "name"):
        op.execute("ALTER TABLE profiles ALTER COLUMN name SET NOT NULL")
        op.execute("ALTER TABLE profiles ALTER COLUMN name SET DEFAULT 'Perfil'")

    # Swap PK from user_id → id (only if it isn't already on `id`).
    pk_col = conn.execute(
        text(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = 'profiles'::regclass AND i.indisprimary"
        )
    ).scalar()
    if pk_col != "id":
        op.execute("ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_pkey")
        op.execute("ALTER TABLE profiles ADD PRIMARY KEY (id)")

    if not _index_exists(conn, "ix_profiles_user_id"):
        op.execute("CREATE INDEX ix_profiles_user_id ON profiles (user_id)")

    # --- 2. search_criteria: add profile_id, backfill, NOT NULL ---------
    if not _column_exists(conn, "search_criteria", "profile_id"):
        op.execute("ALTER TABLE search_criteria ADD COLUMN profile_id UUID")

    # Backfill from user_id → user's only profile (idempotent: only updates nulls).
    conn.execute(
        text(
            "UPDATE search_criteria sc "
            "SET profile_id = p.id "
            "FROM profiles p "
            "WHERE p.user_id = sc.user_id AND sc.profile_id IS NULL"
        )
    )
    if _is_nullable(conn, "search_criteria", "profile_id"):
        op.execute(
            "ALTER TABLE search_criteria ALTER COLUMN profile_id SET NOT NULL"
        )

    if not _constraint_exists(conn, "search_criteria", "fk_search_criteria_profile"):
        op.execute(
            "ALTER TABLE search_criteria "
            "ADD CONSTRAINT fk_search_criteria_profile "
            "FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE"
        )
    if not _index_exists(conn, "ix_search_criteria_profile_id"):
        op.execute(
            "CREATE INDEX ix_search_criteria_profile_id "
            "ON search_criteria (profile_id)"
        )

    # --- 3. user_job_matches: add profile_id, backfill, swap unique -----
    if not _column_exists(conn, "user_job_matches", "profile_id"):
        op.execute("ALTER TABLE user_job_matches ADD COLUMN profile_id UUID")

    # Backfill via criteria_id → profile_id (preferred path).
    conn.execute(
        text(
            "UPDATE user_job_matches m "
            "SET profile_id = sc.profile_id "
            "FROM search_criteria sc "
            "WHERE m.criteria_id = sc.id AND m.profile_id IS NULL"
        )
    )
    # Fallback: via user_id → user's only profile.
    conn.execute(
        text(
            "UPDATE user_job_matches m "
            "SET profile_id = p.id "
            "FROM profiles p "
            "WHERE m.profile_id IS NULL AND p.user_id = m.user_id"
        )
    )
    if _is_nullable(conn, "user_job_matches", "profile_id"):
        op.execute(
            "ALTER TABLE user_job_matches ALTER COLUMN profile_id SET NOT NULL"
        )

    if not _constraint_exists(conn, "user_job_matches", "fk_user_job_matches_profile"):
        op.execute(
            "ALTER TABLE user_job_matches "
            "ADD CONSTRAINT fk_user_job_matches_profile "
            "FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE"
        )
    if not _index_exists(conn, "ix_user_job_matches_profile_id"):
        op.execute(
            "CREATE INDEX ix_user_job_matches_profile_id "
            "ON user_job_matches (profile_id)"
        )

    # Replace unique constraint from (user_id, job_id) to (profile_id, job_id).
    if _constraint_exists(conn, "user_job_matches", "uq_match_user_job"):
        op.execute(
            "ALTER TABLE user_job_matches DROP CONSTRAINT uq_match_user_job"
        )
    if not _constraint_exists(conn, "user_job_matches", "uq_match_profile_job"):
        op.execute(
            "ALTER TABLE user_job_matches "
            "ADD CONSTRAINT uq_match_profile_job UNIQUE (profile_id, job_id)"
        )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_job_matches DROP CONSTRAINT IF EXISTS uq_match_profile_job"
    )
    op.execute(
        "ALTER TABLE user_job_matches "
        "ADD CONSTRAINT uq_match_user_job UNIQUE (user_id, job_id)"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_user_job_matches_profile_id"
    )
    op.execute(
        "ALTER TABLE user_job_matches "
        "DROP CONSTRAINT IF EXISTS fk_user_job_matches_profile"
    )
    op.execute(
        "ALTER TABLE user_job_matches DROP COLUMN IF EXISTS profile_id"
    )

    op.execute("DROP INDEX IF EXISTS ix_search_criteria_profile_id")
    op.execute(
        "ALTER TABLE search_criteria "
        "DROP CONSTRAINT IF EXISTS fk_search_criteria_profile"
    )
    op.execute("ALTER TABLE search_criteria DROP COLUMN IF EXISTS profile_id")

    op.execute("DROP INDEX IF EXISTS ix_profiles_user_id")
    op.execute("ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_pkey")
    op.execute("ALTER TABLE profiles ADD PRIMARY KEY (user_id)")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS name")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS id")
