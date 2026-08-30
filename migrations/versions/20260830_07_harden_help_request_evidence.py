"""Use server receipt time for bounded evidence retention.

Revision ID: 20260830_07
Revises: 20260830_06
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_07"
down_revision: str | None = "20260830_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "help_request_evidence",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE help_request_evidence SET received_at = captured_at WHERE received_at IS NULL",
    )
    op.alter_column("help_request_evidence", "received_at", nullable=False)
    op.drop_index(
        "ix_help_request_evidence_request_captured",
        table_name="help_request_evidence",
    )
    op.create_index(
        "ix_help_request_evidence_request_received",
        "help_request_evidence",
        ["request_id", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_help_request_evidence_request_received",
        table_name="help_request_evidence",
    )
    op.create_index(
        "ix_help_request_evidence_request_captured",
        "help_request_evidence",
        ["request_id", "captured_at"],
        unique=False,
    )
    op.drop_column("help_request_evidence", "received_at")
