"""Create tutorial revision and publication tables.

Revision ID: 20260728_01
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tutorials",
        sa.Column("graph_id", sa.String(length=120), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("graph_id"),
    )
    op.create_table(
        "tutorial_revisions",
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("graph_id", sa.String(length=120), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("graph_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_id"],
            ["tutorials.graph_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("revision_id"),
        sa.UniqueConstraint(
            "graph_id",
            "revision_number",
            name="uq_tutorial_revision_number",
        ),
    )
    op.create_index(
        op.f("ix_tutorial_revisions_graph_id"),
        "tutorial_revisions",
        ["graph_id"],
        unique=False,
    )
    op.create_table(
        "tutorial_publications",
        sa.Column("graph_id", sa.String(length=120), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_id"],
            ["tutorials.graph_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["tutorial_revisions.revision_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("graph_id"),
        sa.UniqueConstraint("revision_id"),
    )


def downgrade() -> None:
    op.drop_table("tutorial_publications")
    op.drop_index(
        op.f("ix_tutorial_revisions_graph_id"),
        table_name="tutorial_revisions",
    )
    op.drop_table("tutorial_revisions")
    op.drop_table("tutorials")
