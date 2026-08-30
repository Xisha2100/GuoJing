"""Add optimistic-concurrency versioning to help-request results.

Revision ID: 20260830_08
Revises: 20260830_07
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_08"
down_revision: str | None = "20260830_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "help_request_results",
        sa.Column("state_version", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE help_request_results SET state_version = 1 WHERE state_version IS NULL",
    )
    op.alter_column("help_request_results", "state_version", nullable=False)


def downgrade() -> None:
    op.drop_column("help_request_results", "state_version")
