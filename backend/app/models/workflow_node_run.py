from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class WorkflowNodeRun(Base):
    __tablename__ = "workflow_node_runs"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "node_id", "attempt", name="uq_node_run_attempt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_release_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_releases.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
