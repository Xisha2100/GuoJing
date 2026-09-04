"""Replace tutorial and help-request storage with visual agent sessions.

Revision ID: 20260904_12
Revises: 20260831_11
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_12"
down_revision: str | None = "20260831_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("help_request_evidence")
    op.drop_table("help_request_results")
    op.drop_table("admin_audit_events")
    op.drop_table("admin_sessions")
    op.drop_table("admin_login_attempts")
    op.drop_table("admin_users")
    op.drop_table("tutorial_draft_workspaces")
    op.drop_table("tutorial_publications")
    op.drop_table("tutorial_revisions")
    op.drop_table("tutorials")

    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("client_session_id", sa.String(length=36), nullable=False),
        sa.Column("access_token_digest", sa.String(length=64), nullable=False),
        sa.Column("goal", sa.String(length=500), nullable=False),
        sa.Column("target_package", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("sandbox_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("client_session_id"),
    )
    op.create_index(
        "ix_agent_session_expires_at",
        "agent_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("client_turn_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("image_media_type", sa.String(length=32), nullable=False),
        sa.Column("screen_width", sa.Integer(), nullable=False),
        sa.Column("screen_height", sa.Integer(), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=True),
        sa.Column("instruction", sa.String(length=300), nullable=True),
        sa.Column("target_left", sa.Float(), nullable=True),
        sa.Column("target_top", sa.Float(), nullable=True),
        sa.Column("target_right", sa.Float(), nullable=True),
        sa.Column("target_bottom", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("session_id", "client_turn_id", name="uq_agent_run_session_turn"),
    )
    op.create_index(
        "ix_agent_run_status_created",
        "agent_runs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "guidance_steps",
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("instruction", sa.String(length=300), nullable=True),
        sa.Column("target_json", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("step_id"),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint("session_id", "step_number", name="uq_guidance_step_number"),
    )


def downgrade() -> None:
    raise RuntimeError("legacy data removal is intentionally irreversible")
