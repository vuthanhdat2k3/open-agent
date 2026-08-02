"""durable execution: tool call records + workflow run lease

Adds the two pieces M14 needs on top of the node-level checkpoint that
``workflow_node_runs.output`` already provides:

* ``tool_call_records`` — recorded tool output so a run can be replayed
  without executing anything again.
* lease/resume columns on ``workflow_runs`` — so a crashed run is picked up
  exactly once, and cannot loop forever.

Revision ID: 0017_durable_execution
Revises: 0016_audit_log_indexes
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0017_durable_execution"
down_revision: str | None = "0016_audit_log_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_call_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            sa.String(length=36),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "node_run_id",
            sa.String(length=36),
            sa.ForeignKey("workflow_node_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "workflow_run_id", "node_run_id", "sequence", name="uq_tool_call_wf_sequence"
        ),
    )
    op.create_index("ix_tool_call_records_org_id", "tool_call_records", ["org_id"])
    op.create_index(
        "ix_tool_call_records_org_session", "tool_call_records", ["org_id", "session_id"]
    )
    op.create_index(
        "ix_tool_call_records_org_workflow", "tool_call_records", ["org_id", "workflow_run_id"]
    )

    op.add_column(
        "workflow_runs",
        sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("workflow_runs", sa.Column("lease_owner", sa.String(length=64), nullable=True))
    op.add_column("workflow_runs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "workflow_runs", sa.Column("replay_of_run_id", sa.String(length=36), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "replay_of_run_id")
    op.drop_column("workflow_runs", "lease_expires_at")
    op.drop_column("workflow_runs", "lease_owner")
    op.drop_column("workflow_runs", "resume_count")

    op.drop_index("ix_tool_call_records_org_workflow", table_name="tool_call_records")
    op.drop_index("ix_tool_call_records_org_session", table_name="tool_call_records")
    op.drop_index("ix_tool_call_records_org_id", table_name="tool_call_records")
    op.drop_table("tool_call_records")
