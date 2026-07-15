"""Ingest job ORM model — tracks asynchronous ingest progress."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from rag_service.db.base import Base


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"job_{uuid4().hex[:8]}"
    )
    document_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("documents.id", ondelete="SET NULL")
    )
    collection_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="queued")
    # 'queued' | 'processing' | 'success' | 'partial' | 'error'
    stage: Mapped[str | None] = mapped_column(Text)  # parsing/chunking/embedding/storing/done
    chunks_total: Mapped[int] = mapped_column(Integer, default=0)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
