from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class OpsFinding(Base):
    """One anomaly the Ops/Reliability agent detected during a scan sweep.

    Always created on a finding (even when the agent has too little
    confidence to attempt a fix) so the diagnosis history is queryable
    independent of parsing chat transcripts - the /ops-health dashboard and
    the Telegram/Discord delivery both read this table directly.
    """

    __tablename__ = "ops_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="reported", nullable=False, index=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    related_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
