from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class AgentRelease(Base):
    __tablename__ = "agent_releases"
    __table_args__ = (
        UniqueConstraint("agent_id", "version", name="uq_agent_releases_agent_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)

    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("models.id"), nullable=False
    )
    tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_risk_tiers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="worker", nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)

    change_note: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

