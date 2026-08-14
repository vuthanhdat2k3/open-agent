"""Add durable workflow schedule state and occurrence idempotency records."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040_workflow_occurrences"
down_revision = "0039_workflow_installations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_installations", sa.Column("next_run_at", sa.DateTime(), nullable=True))
    op.create_index("ix_workflow_installations_next_run_at", "workflow_installations", ["next_run_at"])
    op.create_table(
        "workflow_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("installation_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=True),
        sa.Column("occurrence_key", sa.String(length=160), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["installation_id"], ["workflow_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id", "occurrence_key", name="uq_workflow_occurrence_key"),
        sa.UniqueConstraint("workflow_run_id"),
    )
    op.create_index("ix_workflow_occurrences_installation_id", "workflow_occurrences", ["installation_id"])
    op.create_index("ix_workflow_occurrences_scheduled_for", "workflow_occurrences", ["scheduled_for"])
    op.create_index("ix_workflow_occurrences_status", "workflow_occurrences", ["status"])


def downgrade() -> None:
    op.drop_index("ix_workflow_occurrences_status", table_name="workflow_occurrences")
    op.drop_index("ix_workflow_occurrences_scheduled_for", table_name="workflow_occurrences")
    op.drop_index("ix_workflow_occurrences_installation_id", table_name="workflow_occurrences")
    op.drop_table("workflow_occurrences")
    op.drop_index("ix_workflow_installations_next_run_at", table_name="workflow_installations")
    op.drop_column("workflow_installations", "next_run_at")
