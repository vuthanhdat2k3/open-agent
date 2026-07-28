"""add workspace artifacts and sandbox executions

Revision ID: 0015_workspace_artifacts
Revises: 0014_release_model_nullable
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0015_workspace_artifacts"
down_revision: str | None = "0014_release_model_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("root_run_id", sa.String(length=128), nullable=True),
        sa.Column("source_tool", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "path", name="uq_workspace_artifacts_org_path"),
    )
    op.create_index("ix_workspace_artifacts_agent_id", "workspace_artifacts", ["agent_id"])
    op.create_index("ix_workspace_artifacts_org_id", "workspace_artifacts", ["org_id"])
    op.create_index("ix_workspace_artifacts_root_run_id", "workspace_artifacts", ["root_run_id"])
    op.create_index("ix_workspace_artifacts_session_id", "workspace_artifacts", ["session_id"])
    op.create_index("ix_workspace_artifacts_task_id", "workspace_artifacts", ["task_id"])

    op.create_table(
        "sandbox_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("root_run_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("stdout_preview", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sandbox_executions_agent_id", "sandbox_executions", ["agent_id"])
    op.create_index("ix_sandbox_executions_org_id", "sandbox_executions", ["org_id"])
    op.create_index("ix_sandbox_executions_root_run_id", "sandbox_executions", ["root_run_id"])
    op.create_index("ix_sandbox_executions_session_id", "sandbox_executions", ["session_id"])
    op.create_index("ix_sandbox_executions_status", "sandbox_executions", ["status"])
    op.create_index("ix_sandbox_executions_task_id", "sandbox_executions", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_sandbox_executions_task_id", table_name="sandbox_executions")
    op.drop_index("ix_sandbox_executions_status", table_name="sandbox_executions")
    op.drop_index("ix_sandbox_executions_session_id", table_name="sandbox_executions")
    op.drop_index("ix_sandbox_executions_root_run_id", table_name="sandbox_executions")
    op.drop_index("ix_sandbox_executions_org_id", table_name="sandbox_executions")
    op.drop_index("ix_sandbox_executions_agent_id", table_name="sandbox_executions")
    op.drop_table("sandbox_executions")
    op.drop_index("ix_workspace_artifacts_task_id", table_name="workspace_artifacts")
    op.drop_index("ix_workspace_artifacts_session_id", table_name="workspace_artifacts")
    op.drop_index("ix_workspace_artifacts_root_run_id", table_name="workspace_artifacts")
    op.drop_index("ix_workspace_artifacts_org_id", table_name="workspace_artifacts")
    op.drop_index("ix_workspace_artifacts_agent_id", table_name="workspace_artifacts")
    op.drop_table("workspace_artifacts")
