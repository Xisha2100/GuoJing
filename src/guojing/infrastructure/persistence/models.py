"""SQLAlchemy mappings for the visual guidance agent."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata used by Alembic, not runtime create_all."""


class AgentSessionRecord(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (Index("ix_agent_session_expires_at", "expires_at"),)

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_session_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    access_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    goal: Mapped[str] = mapped_column(String(500), nullable=False)
    target_package: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    current_step: Mapped[int] = mapped_column(nullable=False)
    sandbox_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("session_id", "client_turn_id", name="uq_agent_run_session_turn"),
        Index("ix_agent_run_status_created", "status", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    client_turn_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    screen_width: Mapped[int] = mapped_column(nullable=False)
    screen_height: Mapped[int] = mapped_column(nullable=False)
    result_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    instruction: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_left: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_top: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_right: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_bottom: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retryable: Mapped[bool] = mapped_column(nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuidanceStepRecord(Base):
    __tablename__ = "guidance_steps"
    __table_args__ = (
        UniqueConstraint("session_id", "step_number", name="uq_guidance_step_number"),
    )

    step_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    step_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    instruction: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
