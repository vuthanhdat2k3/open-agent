from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class OutboxEvent(Base):
    """Durable application event; Redis/ARQ is only its transport."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("event_type", "dedupe_key", name="uq_outbox_event_type_dedupe"),
        Index("ix_outbox_events_dispatch", "status", "available_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    causation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class ProcessedEvent(Base):
    """Consumer receipt used to make at-least-once delivery safe."""

    __tablename__ = "processed_events"
    __table_args__ = (
        UniqueConstraint("event_id", "consumer_name", name="uq_processed_event_consumer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    consumer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
