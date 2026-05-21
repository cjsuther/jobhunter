"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-05-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("full_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("full_name", sa.String(255)),
        sa.Column("headline", sa.String(500)),
        sa.Column("current_location", sa.String(255)),
        sa.Column("years_experience", sa.Integer),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("phone", sa.String(50)),
        sa.Column("email_contact", sa.String(255)),
        sa.Column(
            "cv_base_json",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cv_base_pdf_path", sa.String(500)),
        sa.Column("about_text", sa.Text),
        sa.Column("preferred_titles", postgresql.ARRAY(sa.String)),
        sa.Column("excluded_companies", postgresql.ARRAY(sa.String)),
        sa.Column("excluded_keywords", postgresql.ARRAY(sa.String)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "search_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100)),
        sa.Column("keywords", postgresql.ARRAY(sa.String)),
        sa.Column("locations", postgresql.ARRAY(sa.String)),
        sa.Column("modalities", postgresql.ARRAY(sa.String)),
        sa.Column("seniority_levels", postgresql.ARRAY(sa.String)),
        sa.Column("salary_min_ars", sa.BigInteger),
        sa.Column("contract_types", postgresql.ARRAY(sa.String)),
        sa.Column("min_fit_score", sa.Integer, nullable=False, server_default="70"),
        sa.Column("daily_apply_cap", sa.Integer, nullable=False, server_default="10"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "portals_enabled",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_search_criteria_user_id", "search_criteria", ["user_id"])

    op.create_table(
        "portal_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("portal", sa.String(50), nullable=False),
        sa.Column("encrypted_cookies", sa.LargeBinary),
        sa.Column("encrypted_credentials", sa.LargeBinary),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("user_id", "portal", name="uq_portal_session_user_portal"),
    )
    op.create_index("ix_portal_sessions_user_id", "portal_sessions", ["user_id"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_portal", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("external_url", sa.Text, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("modality", sa.String(50)),
        sa.Column("description", sa.Text),
        sa.Column("description_hash", sa.String(64)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("application_type", sa.String(50)),
        sa.Column("raw_json", postgresql.JSONB),
        sa.UniqueConstraint("source_portal", "external_id", name="uq_jobs_portal_external"),
    )
    op.create_index("ix_jobs_source_portal", "jobs", ["source_portal"])
    op.create_index("ix_jobs_description_hash", "jobs", ["description_hash"])

    op.create_table(
        "user_job_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "criteria_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("search_criteria.id", ondelete="SET NULL"),
        ),
        sa.Column("fit_score", sa.Integer, nullable=False),
        sa.Column("scoring_reasoning", sa.Text),
        sa.Column("strengths", postgresql.ARRAY(sa.String)),
        sa.Column("red_flags", postgresql.ARRAY(sa.String)),
        sa.Column("recommended_action", sa.String(20)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("user_notes", sa.Text),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "job_id", name="uq_match_user_job"),
    )
    op.create_index("ix_user_job_matches_user_id", "user_job_matches", ["user_id"])
    op.create_index("ix_user_job_matches_job_id", "user_job_matches", ["job_id"])
    op.create_index("ix_user_job_matches_status", "user_job_matches", ["status"])

    op.create_table(
        "generated_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "match_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_job_matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("pdf_path", sa.String(500)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("model_used", sa.String(100)),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_generated_materials_match_id", "generated_materials", ["match_id"])

    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "match_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_job_matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(50)),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "cv_material_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generated_materials.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "letter_material_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generated_materials.id", ondelete="SET NULL"),
        ),
        sa.Column("response_received_at", sa.DateTime(timezone=True)),
        sa.Column("response_type", sa.String(50)),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_applications_match_id", "applications", ["match_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("applications")
    op.drop_table("generated_materials")
    op.drop_table("user_job_matches")
    op.drop_table("jobs")
    op.drop_table("portal_sessions")
    op.drop_table("search_criteria")
    op.drop_table("profiles")
    op.drop_table("users")
