from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

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
