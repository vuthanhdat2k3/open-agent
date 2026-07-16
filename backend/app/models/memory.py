from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
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


class AgentMemory(Base):
    """Structured, long-lived memory scoped to an agent (phase-1 owner).

    Schema is fixed: (agent_id, memory_type, attribute) is unique so writes
    UPSERT instead of duplicating. `owner_type` is a forward-compatible column
    (future: 'user' / 'workspace') but phase 1 always uses 'agent'.
    """

    __tablename__ = "agent_memories"
    __table_args__ = (
        UniqueConstraint(
            "agent_id", "memory_type", "attribute", name="uq_agent_memory"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id"), nullable=False, index=True
    )
    owner_type: Mapped[str] = mapped_column(String(32), default="agent", nullable=False)

    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    attribute: Mapped[str] = mapped_column(String(128), nullable=False)

    value: Mapped[str] = mapped_column(Text, nullable=False)

    importance: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="agent", nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)

    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class SessionMemory(Base):
    __tablename__ = "session_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
