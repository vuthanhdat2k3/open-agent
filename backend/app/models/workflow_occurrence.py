from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class WorkflowOccurrence(Base):
    """Durable idempotency record for one scheduled workflow occurrence."""

    __tablename__ = "workflow_occurrences"
    __table_args__ = (
        UniqueConstraint("installation_id", "occurrence_key", name="uq_workflow_occurrence_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    installation_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_installations.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, unique=True)
    occurrence_key: Mapped[str] = mapped_column(String(160), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
