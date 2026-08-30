"""Persist safe workflow stages and tutorial match metadata.

Revision ID: 20260830_06
Revises: 20260830_05
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_06"
down_revision: str | None = "20260830_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "help_request_results",
        sa.Column("workflow_stage", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "help_request_results",
        sa.Column("tutorial_match_status", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "help_request_results",
        sa.Column("tutorial_match_reason", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "help_request_results",
        sa.Column("tutorial_graph_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "help_request_results",
        sa.Column("tutorial_node_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "help_request_results",
        sa.Column("tutorial_revision_number", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("help_request_results", "tutorial_revision_number")
    op.drop_column("help_request_results", "tutorial_node_id")
    op.drop_column("help_request_results", "tutorial_graph_id")
    op.drop_column("help_request_results", "tutorial_match_reason")
    op.drop_column("help_request_results", "tutorial_match_status")
    op.drop_column("help_request_results", "workflow_stage")
