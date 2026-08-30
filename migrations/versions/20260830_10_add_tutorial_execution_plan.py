"""Persist pinned tutorial execution plans for help requests.

Revision ID: 20260830_10
Revises: 20260830_09
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_10"
down_revision: str | None = "20260830_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "help_request_results",
        sa.Column("tutorial_plan_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("help_request_results", "tutorial_plan_json")
