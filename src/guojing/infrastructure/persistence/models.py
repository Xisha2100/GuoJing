"""SQLAlchemy mappings for tutorial persistence."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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


class AdminUserRecord(Base):
    __tablename__ = "admin_users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminSessionRecord(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_admin_session_expiry"),)

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    admin_user_id: Mapped[str] = mapped_column(
        ForeignKey("admin_users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminLoginAttemptRecord(Base):
    __tablename__ = "admin_login_attempts"
    __table_args__ = (Index("ix_admin_login_attempt_username_time", "username", "occurred_at"),)

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAuditEventRecord(Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (Index("ix_admin_audit_event_occurred_at", "occurred_at"),)

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    admin_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("admin_users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)


class HelpRequestResultRecord(Base):
    """Persist lifecycle metadata without retaining the submitted screenshot."""

    __tablename__ = "help_request_results"
    __table_args__ = (
        Index(
            "ix_help_request_result_status_updated",
            "processing_status",
            "updated_at",
        ),
        Index("ix_help_request_result_expires_at", "expires_at"),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_request_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_route: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(40), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state_version: Mapped[int] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    guidance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tutorial_match_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tutorial_match_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tutorial_graph_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tutorial_node_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tutorial_revision_number: Mapped[int | None] = mapped_column(nullable=True)


class HelpRequestEvidenceRecord(Base):
    """Persist only normalized anchor evidence, never OCR or node-tree text."""

    __tablename__ = "help_request_evidence"
    __table_args__ = (
        Index(
            "ix_help_request_evidence_request_received",
            "request_id",
            "received_at",
        ),
        Index("ix_help_request_evidence_expires_at", "expires_at"),
    )

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("help_request_results.request_id", ondelete="CASCADE"),
        nullable=False,
    )
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version_code: Mapped[int] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    sharing_policy: Mapped[str] = mapped_column(String(40), nullable=False)
    structure_score: Mapped[float] = mapped_column(nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    anchors_json: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_screenshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
