"""Create TTL-bound help request result metadata table.

Revision ID: 20260830_04
Revises: 20260802_03
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_04"
down_revision: str | None = "20260802_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_request_results",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("client_request_id", sa.String(length=36), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("processing_route", sa.String(length=40), nullable=False),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("guidance_json", sa.Text(), nullable=True),
        sa.Column("human_review_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint("client_request_id"),
    )
    op.create_index(
        "ix_help_request_result_status_updated",
        "help_request_results",
        ["processing_status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_help_request_result_expires_at",
        "help_request_results",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_help_request_result_expires_at",
        table_name="help_request_results",
    )
    op.drop_index(
        "ix_help_request_result_status_updated",
        table_name="help_request_results",
    )
    op.drop_table("help_request_results")
