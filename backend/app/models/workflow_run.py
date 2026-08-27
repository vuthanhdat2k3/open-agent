from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False, index=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Immutable execution context. A run must not change behavior when the
    # editable workflow is updated while it is running or waiting for approval.
    graph_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    graph_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trigger_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Durable execution (M14) ---
    # How many times a worker has picked this run back up after a crash.
    # Bounded so a run that dies at the same node cannot loop forever.
    resume_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Optimistic DB-level lease: only the worker that wins the conditional
    # UPDATE may execute the run, which stops two workers double-running the
    # same nodes after a restart.
    # ponytail: DB lease is enough at current scale; move to a Redis lock if
    # lease contention ever shows up in metrics.
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Set when this run is a deterministic replay of an earlier one.
    # Deliberately not a foreign key: the original run may be pruned by
    # retention while the replay is still worth keeping, and a
    # self-referential FK makes schema migrations painful on SQLite.
    replay_of_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

