from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_agents_org_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model_id: Mapped[str | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_risk_tiers: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["safe", "read"]
    )
    kind: Mapped[str] = mapped_column(String(32), default="worker", nullable=False)
    # "all" (default, current behavior - every role that can chat sees it) or
    # "platform_admin" (hidden from listing/session-creation for every other
    # role, enforced server-side, not just a frontend filter - see
    # dependencies.py's require_agent_visible / routes/agents.py).
    visibility: Mapped[str] = mapped_column(String(16), default="all", nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=12)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    enable_thinking: Mapped[bool | None] = mapped_column(nullable=True)
    active_release_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_releases.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    latest_release_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- Auto-rollback (M15) ---
    # Off by default: automatically swapping the production release out is
    # a strong action and must be an explicit opt-in per agent.
    auto_rollback_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Falls back to the suite's own min_pass_rate when unset.
    auto_rollback_min_pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_rollback_cooldown_minutes: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )

    # --- A2A Exposure (M16) ---
    a2a_exposed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- System Templates & Hybrid Resolution ---
    template_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_customized: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
