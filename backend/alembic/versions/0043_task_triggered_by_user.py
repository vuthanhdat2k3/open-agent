"""Add task ownership for run authorization.

Revision ID: 0043_task_triggered_by_user
Revises: 0042_archive_workflow_installations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_task_triggered_by_user"
down_revision: str | None = "0042_archive_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(
            sa.Column("triggered_by_user_id", sa.String(length=36), nullable=True)
        )
        batch.create_foreign_key(
            "fk_tasks_triggered_by_user_id_users",
            "users",
            ["triggered_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_tasks_triggered_by_user_id", "tasks", ["triggered_by_user_id"], unique=False
    )

    # Preserve access to historical runs where ownership can be derived from
    # the session embedded in task.progress, the workflow run, or a parent
    # task. Leave genuinely ambiguous machine tasks NULL: the application
    # intentionally fails closed for non-admin principals in that case.
    conn = op.get_bind()
    tasks = sa.table(
        "tasks",
        sa.column("id", sa.String()),
        sa.column("org_id", sa.String()),
        sa.column("parent_task_id", sa.String()),
        sa.column("root_run_id", sa.String()),
        sa.column("progress", sa.JSON()),
        sa.column("triggered_by_user_id", sa.String()),
    )
    sessions = sa.table(
        "sessions",
        sa.column("id", sa.String()),
        sa.column("org_id", sa.String()),
        sa.column("created_by_user_id", sa.String()),
    )
    workflow_runs = sa.table(
        "workflow_runs",
        sa.column("id", sa.String()),
        sa.column("org_id", sa.String()),
        sa.column("triggered_by_user_id", sa.String()),
    )

    session_owners = {
        (row.org_id, row.id): row.created_by_user_id
        for row in conn.execute(
            sa.select(sessions.c.org_id, sessions.c.id, sessions.c.created_by_user_id)
        )
        if row.created_by_user_id
    }
    workflow_owners = {
        (row.org_id, row.id): row.triggered_by_user_id
        for row in conn.execute(
            sa.select(
                workflow_runs.c.org_id,
                workflow_runs.c.id,
                workflow_runs.c.triggered_by_user_id,
            )
        )
        if row.triggered_by_user_id
    }
    pending = list(
        conn.execute(
            sa.select(
                tasks.c.id,
                tasks.c.org_id,
                tasks.c.parent_task_id,
                tasks.c.root_run_id,
                tasks.c.progress,
            ).where(tasks.c.triggered_by_user_id.is_(None))
        ).mappings()
    )
    owners_by_task: dict[str, str] = {}
    for row in pending:
        progress = row["progress"] or {}
        session_id = progress.get("session_id") if isinstance(progress, dict) else None
        owner = session_owners.get((row["org_id"], session_id)) if session_id else None
        owner = owner or workflow_owners.get((row["org_id"], row["root_run_id"]))
        if owner:
            owners_by_task[row["id"]] = owner

    # Resolve nested historical tasks from their already-resolved parent.
    changed = True
    while changed:
        changed = False
        for row in pending:
            if row["id"] in owners_by_task or not row["parent_task_id"]:
                continue
            owner = owners_by_task.get(row["parent_task_id"])
            if owner:
                owners_by_task[row["id"]] = owner
                changed = True

    for task_id, user_id in owners_by_task.items():
        conn.execute(
            tasks.update()
            .where(tasks.c.id == task_id, tasks.c.triggered_by_user_id.is_(None))
            .values(triggered_by_user_id=user_id)
        )


def downgrade() -> None:
    op.drop_index("ix_tasks_triggered_by_user_id", table_name="tasks")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_triggered_by_user_id_users", type_="foreignkey")
        batch.drop_column("triggered_by_user_id")
