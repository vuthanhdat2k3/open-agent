from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now

# Which production signals are worth turning into a regression test. Ordered
# by how strongly each one indicates a real defect.
DEFAULT_SAMPLING_REASONS = [
    "guardrail_injection_flagged",
    "guardrail_secret_redacted",
    "run_failed",
    "tool_error",
    "max_iterations_reached",
]


class SamplingPolicy(Base):
    """Rules for turning production traces into proposed evaluation cases.

    Disabled by default: sampling reads real conversations, so an operator
    has to opt in per agent rather than discovering after the fact that
    production traffic is being copied into a dataset.
    """

    __tablename__ = "sampling_policies"
    __table_args__ = (
        UniqueConstraint("org_id", "agent_id", "suite_id", name="uq_sampling_policy_target"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_suites.id", ondelete="CASCADE"), nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Caps dataset growth: an agent having a bad day would otherwise bury the
    # suite in near-identical cases nobody will ever review.
    max_per_day: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
