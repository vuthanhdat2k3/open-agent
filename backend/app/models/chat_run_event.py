from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class ChatRunEvent(Base):
    """Append-only event log for a chat run (``tasks.root_run_id``).

    Every SSE-shaped event the agent loop emits while a chat run is in flight
    is persisted here. After a page reload (or a new tab/device) the client
    drains the log and rebuilds the exact UI position — partial assistant
    text, reasoning in progress, running tool cards, live tool progress —
    then tails new events, instead of waiting blind until ``message_done``.

    Kept separate from ``messages``: events are ephemeral, per-run and
    high-frequency; messages are the durable per-session transcript.
    """

    __tablename__ = "chat_run_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(48), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        Index("ix_chat_run_events_run_seq", "run_id", "seq", unique=True),
        Index("ix_chat_run_events_org_run", "org_id", "run_id"),
    )
