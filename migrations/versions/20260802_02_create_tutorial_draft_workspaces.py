"""Create versioned tutorial draft workspaces.

Revision ID: 20260802_02
Revises: 20260728_01
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_02"
down_revision: str | None = "20260728_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tutorial_draft_workspaces",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("promoted_graph_id", sa.String(length=120), nullable=True),
        sa.Column("promoted_revision_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(promoted_graph_id IS NULL AND promoted_revision_number IS NULL) OR "
            "(promoted_graph_id IS NOT NULL AND promoted_revision_number IS NOT NULL)",
            name="ck_draft_workspace_complete_promotion",
        ),
        sa.CheckConstraint(
            "promoted_revision_number IS NULL OR promoted_revision_number >= 1",
            name="ck_draft_workspace_positive_promotion_revision",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_draft_workspace_positive_version",
        ),
        sa.ForeignKeyConstraint(
            ["promoted_graph_id", "promoted_revision_number"],
            [
                "tutorial_revisions.graph_id",
                "tutorial_revisions.revision_number",
            ],
            name="fk_draft_workspace_promoted_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("tutorial_draft_workspaces")
