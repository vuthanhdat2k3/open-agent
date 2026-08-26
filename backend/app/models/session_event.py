from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class SessionEvent(Base):
    """Append-only event log for a chat session.

    The durable source of truth for conversation history: every model-visible
    fact (user/assistant messages, tool calls and results, compaction
    summaries) is appended here and the provider request history is *derived*
    from this log — never assembled ad hoc. "Model-visible means logged."

    Kept separate from ``messages`` (the UI-facing transcript with only final
    user/assistant text): the event log preserves full tool-call fidelity so
    later turns see exactly what earlier turns did.
    """

    __tablename__ = "session_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # "user/message" | "assistant/message" | "tool/call" | "tool/result"
    # | "compaction/summary"
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        Index("ix_session_events_session_seq", "session_id", "seq", unique=True),
        Index("ix_session_events_org_session", "org_id", "session_id"),
    )
