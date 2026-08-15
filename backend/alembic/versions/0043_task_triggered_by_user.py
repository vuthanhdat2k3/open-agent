"""Add task ownership for run authorization.

Revision ID: 0043_task_triggered_by_user
Revises: 0042_archive_workflow_installations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_task_triggered_by_user"
down_revision: str | None = "0042_archive_workflow_installations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("triggered_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_tasks_triggered_by_user_id_users",
        "tasks",
        "users",
        ["triggered_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tasks_triggered_by_user_id", "tasks", ["triggered_by_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_triggered_by_user_id", table_name="tasks")
    op.drop_constraint("fk_tasks_triggered_by_user_id_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "triggered_by_user_id")
