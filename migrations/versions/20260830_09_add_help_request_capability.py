"""Bind help-request reads and evidence writes to a capability.

Revision ID: 20260830_09
Revises: 20260830_08
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_09"
down_revision: str | None = "20260830_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "help_request_results",
        sa.Column("access_token_digest", sa.String(length=64), nullable=True),
    )
    # Existing pre-capability requests cannot be safely attributed, so they are
    # deliberately invalidated rather than made readable with a shared default.
    op.execute("DELETE FROM help_request_results")
    op.alter_column("help_request_results", "access_token_digest", nullable=False)


def downgrade() -> None:
    op.drop_column("help_request_results", "access_token_digest")
