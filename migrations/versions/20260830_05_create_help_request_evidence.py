"""Create bounded help-request evidence envelopes.

Revision ID: 20260830_05
Revises: 20260830_04
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_05"
down_revision: str | None = "20260830_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_request_evidence",
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("version_name", sa.String(length=120), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("sharing_policy", sa.String(length=40), nullable=False),
        sa.Column("structure_score", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchors_json", sa.Text(), nullable=False),
        sa.Column("sanitized_screenshot_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["help_request_results.request_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index(
        "ix_help_request_evidence_request_captured",
        "help_request_evidence",
        ["request_id", "captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_help_request_evidence_expires_at",
        "help_request_evidence",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_help_request_evidence_expires_at",
        table_name="help_request_evidence",
    )
    op.drop_index(
        "ix_help_request_evidence_request_captured",
        table_name="help_request_evidence",
    )
    op.drop_table("help_request_evidence")
