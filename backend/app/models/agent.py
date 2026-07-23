from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), nullable=False)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_risk_tiers: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["safe", "read"]
    )
    kind: Mapped[str] = mapped_column(String(32), default="worker", nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=12)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
