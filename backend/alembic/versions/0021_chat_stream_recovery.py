"""chat stream recovery: per-run event log + task progress

Adds durable in-flight state for chat so a page reload can rebuild the exact
stream position instead of waiting until the run finishes:

* ``chat_run_events`` — append-only SSE-shaped event log per chat run
  (``tasks.root_run_id``). The agent loop writes every event it emits; the
  client drains the log and follows new events.
* ``tasks.progress`` — small JSON checkpoint (last emitted seq + last
  content/reasoning/tool activity) so polling clients can render a live
  indicator without touching the event log, and orphaned runs can be told
  apart from merely slow ones.

Revision ID: 0021_chat_stream_recovery
Revises: 0020_a2a_and_agent_identity
Create Date: 2026-08-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0021_chat_stream_recovery"
down_revision: str | None = "0020_a2a_and_agent_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_run_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=48), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("run_id", "seq", name="uq_chat_run_events_run_seq"),
    )
    op.create_index(
        "ix_chat_run_events_run_seq", "chat_run_events", ["run_id", "seq"], unique=True
    )
    op.create_index("ix_chat_run_events_org_run", "chat_run_events", ["org_id", "run_id"])

    op.add_column("tasks", sa.Column("progress", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "progress")

    op.drop_index("ix_chat_run_events_org_run", table_name="chat_run_events")
    op.drop_index("ix_chat_run_events_run_seq", table_name="chat_run_events")
    op.drop_table("chat_run_events")
