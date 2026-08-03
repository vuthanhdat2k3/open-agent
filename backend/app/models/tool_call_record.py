from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class ToolCallRecord(Base):
    """One recorded tool invocation, used to replay a run deterministically.

    Replay reads these back in ``sequence`` order instead of executing the
    tool again, so reproducing a non-deterministic run costs nothing and
    causes no side effects.

    ``workflow_run_id``/``node_run_id`` are null for plain chat sessions and
    ``session_id`` is null for workflow runs — a record always belongs to
    exactly one of the two execution paths.
    """

    __tablename__ = "tool_call_records"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "node_run_id", "sequence", name="uq_tool_call_wf_sequence"
        ),
        Index("ix_tool_call_records_org_session", "org_id", "session_id"),
        Index("ix_tool_call_records_org_workflow", "org_id", "workflow_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True
    )
    node_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflow_node_runs.id", ondelete="CASCADE"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Position of this call within its run; replay matches on it so the same
    # tool called twice with different arguments stays distinguishable.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # sha256 of the canonical (key-sorted) argument JSON — lets replay detect
    # that the model asked for the same tool with different arguments.
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="ok", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
