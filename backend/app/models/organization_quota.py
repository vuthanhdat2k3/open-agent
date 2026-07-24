from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class OrganizationQuota(Base):
    __tablename__ = "organization_quotas"

    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_runs_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    max_concurrent_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    max_agents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_workflows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_storage_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enforcement_mode: Mapped[str] = mapped_column(
        String(16), default="enforce", nullable=False
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
