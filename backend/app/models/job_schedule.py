from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class JobScheduleExecution(Base):
    """Durable claim/result record for one scheduled job tick."""

    __tablename__ = "job_schedule_executions"
    __table_args__ = (
        UniqueConstraint("job_key", "scheduled_for", name="uq_job_schedule_key_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="running", server_default="running", index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
