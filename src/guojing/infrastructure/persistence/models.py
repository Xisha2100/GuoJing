"""SQLAlchemy mappings for tutorial persistence."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
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
