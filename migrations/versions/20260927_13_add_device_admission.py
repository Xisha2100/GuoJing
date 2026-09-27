"""Add invited devices and transactionally reserved daily usage.

Revision ID: 20260927_13
Revises: 20260904_12
"""

import sqlalchemy as sa
from alembic import op

revision = "20260927_13"
down_revision = "20260904_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_sessions", sa.Column("device_id", sa.String(36), nullable=True))
    op.create_index("ix_agent_sessions_device_id", "agent_sessions", ["device_id"])
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(36), primary_key=True),
        sa.Column("installation_id", sa.String(36), nullable=False, unique=True),
        sa.Column("secret_digest", sa.String(64), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "device_invitations",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=True),
    )
    op.create_table(
        "daily_usage",
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("scope", sa.String(36), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "run_reservations",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
    )
    op.create_index("ix_run_reservations_device_id", "run_reservations", ["device_id"])
    op.create_table(
        "operations",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("value", sa.String(120), nullable=False),
    )
    # Anonymous historical sessions cannot acquire an owner during this migration.
    op.execute("UPDATE agent_sessions SET status='closed' WHERE device_id IS NULL")


def downgrade() -> None:
    for name in ("operations", "run_reservations", "daily_usage", "device_invitations", "devices"):
        op.drop_table(name)
    op.drop_index("ix_agent_sessions_device_id", table_name="agent_sessions")
    op.drop_column("agent_sessions", "device_id")
