"""add task table and agent kind

Revision ID: 0007_add_tasks_and_agent_kind
Revises: 0006_add_approval_requests
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_add_tasks_and_agent_kind"
down_revision: str | None = "0006_add_approval_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("agents"):
        agent_cols = [c["name"] for c in inspector.get_columns("agents")]
        if "kind" not in agent_cols:
            op.add_column("agents", sa.Column("kind", sa.String(length=32), nullable=True))
            op.execute("UPDATE agents SET kind = 'worker' WHERE kind IS NULL")

    if not inspector.has_table("tasks"):
        op.create_table(
            "tasks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("parent_task_id", sa.String(length=36), nullable=True),
            sa.Column("root_run_id", sa.String(length=128), nullable=False),
            sa.Column("agent_id", sa.String(length=36), nullable=False),
            sa.Column("goal", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("cost_usd", sa.Float(), nullable=True),
            sa.Column("token_usage", sa.JSON(), nullable=True),
            sa.Column("depth", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_tasks_org_id"), "tasks", ["org_id"], unique=False)
        op.create_index(op.f("ix_tasks_parent_task_id"), "tasks", ["parent_task_id"], unique=False)
        op.create_index(op.f("ix_tasks_root_run_id"), "tasks", ["root_run_id"], unique=False)
        op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("tasks"):
        op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
        op.drop_index(op.f("ix_tasks_root_run_id"), table_name="tasks")
        op.drop_index(op.f("ix_tasks_parent_task_id"), table_name="tasks")
        op.drop_index(op.f("ix_tasks_org_id"), table_name="tasks")
        op.drop_table("tasks")

    if inspector.has_table("agents"):
        agent_cols = [c["name"] for c in inspector.get_columns("agents")]
        if "kind" in agent_cols:
            op.drop_column("agents", "kind")

