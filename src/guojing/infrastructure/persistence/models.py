"""SQLAlchemy mappings for tutorial persistence."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata used by Alembic, not runtime create_all."""


class TutorialRecord(Base):
    __tablename__ = "tutorials"

    graph_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TutorialRevisionRecord(Base):
    __tablename__ = "tutorial_revisions"
    __table_args__ = (
        UniqueConstraint("graph_id", "revision_number", name="uq_tutorial_revision_number"),
    )

    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("tutorials.graph_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(nullable=False)
    graph_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TutorialPublicationRecord(Base):
    __tablename__ = "tutorial_publications"

    graph_id: Mapped[str] = mapped_column(
        ForeignKey("tutorials.graph_id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("tutorial_revisions.revision_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TutorialDraftWorkspaceRecord(Base):
    __tablename__ = "tutorial_draft_workspaces"
    __table_args__ = (
        ForeignKeyConstraint(
            ["promoted_graph_id", "promoted_revision_number"],
            [
                "tutorial_revisions.graph_id",
                "tutorial_revisions.revision_number",
            ],
            name="fk_draft_workspace_promoted_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="ck_draft_workspace_positive_version"),
        CheckConstraint(
            "(promoted_graph_id IS NULL AND promoted_revision_number IS NULL) OR "
            "(promoted_graph_id IS NOT NULL AND promoted_revision_number IS NOT NULL)",
            name="ck_draft_workspace_complete_promotion",
        ),
        CheckConstraint(
            "promoted_revision_number IS NULL OR promoted_revision_number >= 1",
            name="ck_draft_workspace_positive_promotion_revision",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)
    promoted_graph_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    promoted_revision_number: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
