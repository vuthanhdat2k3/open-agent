"""Add owning_task_id to approval_requests for correct multi-level delegation resume.

Revision ID: 0027_approval_owning_task
Revises: 0026_provider_templates

Explicit ownership routing: an approval raised inside a delegated sub-agent
(call_agent / delegate_to_*) must resume in that sub-agent's task, not the
root task's — resuming the wrong one either fails ("tool not available" if
the root doesn't have that tool) or silently strands the sub-task. NULL
means "the root task" (pre-existing rows, and direct non-delegated
approvals), preserving current behavior for anything already pending.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_approval_owning_task"
down_revision = "0026_provider_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("owning_task_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_approval_requests_owning_task_id",
        "approval_requests",
        ["owning_task_id"],
    )
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.create_foreign_key(
            "fk_approval_requests_owning_task_id",
            "tasks",
            ["owning_task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.drop_constraint("fk_approval_requests_owning_task_id", type_="foreignkey")
    op.drop_index("ix_approval_requests_owning_task_id", table_name="approval_requests")
    op.drop_column("approval_requests", "owning_task_id")
