"""Create administrator identity, session, throttling, and audit tables.

Revision ID: 20260802_03
Revises: 20260802_02
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_03"
down_revision: str | None = "20260802_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "admin_login_attempts",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_admin_login_attempt_username_time",
        "admin_login_attempts",
        ["username", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "admin_sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("admin_user_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_admin_session_expiry"),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("session_token_hash"),
    )
    op.create_index(
        op.f("ix_admin_sessions_admin_user_id"),
        "admin_sessions",
        ["admin_user_id"],
        unique=False,
    )
    op.create_table(
        "admin_audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("admin_user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        op.f("ix_admin_audit_events_admin_user_id"),
        "admin_audit_events",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_event_occurred_at",
        "admin_audit_events",
        ["occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_audit_event_occurred_at",
        table_name="admin_audit_events",
    )
    op.drop_index(
        op.f("ix_admin_audit_events_admin_user_id"),
        table_name="admin_audit_events",
    )
    op.drop_table("admin_audit_events")
    op.drop_index(
        op.f("ix_admin_sessions_admin_user_id"),
        table_name="admin_sessions",
    )
    op.drop_table("admin_sessions")
    op.drop_index(
        "ix_admin_login_attempt_username_time",
        table_name="admin_login_attempts",
    )
    op.drop_table("admin_login_attempts")
    op.drop_table("admin_users")
