from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"), nullable=False
    )
    # "user" | "assistant" | "tool_call" | "tool_result"
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    # structured payload: tool name/args, meta badges, token usage, etc.
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
