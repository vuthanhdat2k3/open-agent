"""Add generic scheduled-job leases and Customer Intelligence retry state."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_job_scheduling_hardening"
down_revision = "0029_context_window_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_schedule_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_key", sa.String(length=64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("job_key", "scheduled_for", name="uq_job_schedule_key_time"),
    )
    op.create_index(
        "ix_job_schedule_executions_job_key",
        "job_schedule_executions",
        ["job_key"],
    )
    op.create_index(
        "ix_job_schedule_executions_status",
        "job_schedule_executions",
        ["status"],
    )

    op.add_column(
        "ci_cases",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("ci_cases", sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    op.add_column(
        "ci_cases",
        sa.Column("last_retry_triggered_by", sa.String(length=36), nullable=True),
    )
    with op.batch_alter_table("ci_cases") as batch_op:
        batch_op.create_foreign_key(
            "fk_ci_cases_last_retry_triggered_by",
            "users",
            ["last_retry_triggered_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("ci_cases") as batch_op:
        batch_op.drop_constraint("fk_ci_cases_last_retry_triggered_by", type_="foreignkey")
    op.drop_column("ci_cases", "last_retry_triggered_by")
    op.drop_column("ci_cases", "next_retry_at")
    op.drop_column("ci_cases", "retry_count")
    op.drop_index("ix_job_schedule_executions_status", table_name="job_schedule_executions")
    op.drop_index("ix_job_schedule_executions_job_key", table_name="job_schedule_executions")
    op.drop_table("job_schedule_executions")
