"""Retain bounded help-request context and overlapping capability digests.

Revision ID: 20260831_11
Revises: 20260830_10
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_11"
down_revision: str | None = "20260830_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "help_request_results",
        sa.Column("question", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "help_request_results",
        sa.Column("access_token_digests_json", sa.Text(), nullable=True),
    )
    # Existing rows have one digest.  Copy it into the overlap list so the
    # new reader can handle old records without invalidating their capability.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE help_request_results "
            "SET access_token_digests_json = '[\"' || access_token_digest || '\"]' "
            "WHERE access_token_digests_json IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("help_request_results", "access_token_digests_json")
    op.drop_column("help_request_results", "question")
