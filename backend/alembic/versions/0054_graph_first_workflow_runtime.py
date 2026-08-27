"""Add graph-first workflow run metadata and trigger projection."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_graph_first_workflow_runtime"
down_revision: str | tuple[str, str] | None = "0053_merge_workflow_and_session_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("graph_snapshot", sa.JSON(), nullable=True))
    op.add_column("workflow_runs", sa.Column("graph_hash", sa.String(length=64), nullable=True))
    op.add_column("workflow_runs", sa.Column("trigger_node_id", sa.String(length=128), nullable=True))
    op.add_column("workflow_runs", sa.Column("trigger_type", sa.String(length=32), nullable=True))
    op.add_column("workflow_runs", sa.Column("trigger_occurrence_key", sa.String(length=192), nullable=True))
    op.create_index(
        "uq_workflow_run_trigger_occurrence",
        "workflow_runs",
        ["trigger_occurrence_key"],
        unique=True,
    )

    op.create_table(
        "workflow_trigger_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("schedule_hash", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "workflow_id", "node_id", name="uq_workflow_trigger_state_node"),
    )
    op.create_index(
        "ix_workflow_trigger_states_org_id", "workflow_trigger_states", ["org_id"], unique=False
    )
    op.create_index(
        "ix_workflow_trigger_states_workflow_id", "workflow_trigger_states", ["workflow_id"], unique=False
    )
    op.create_index(
        "ix_workflow_trigger_states_enabled", "workflow_trigger_states", ["enabled"], unique=False
    )
    op.create_index(
        "ix_workflow_trigger_states_next_run_at", "workflow_trigger_states", ["next_run_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_trigger_states_next_run_at", table_name="workflow_trigger_states")
    op.drop_index("ix_workflow_trigger_states_enabled", table_name="workflow_trigger_states")
    op.drop_index("ix_workflow_trigger_states_workflow_id", table_name="workflow_trigger_states")
    op.drop_index("ix_workflow_trigger_states_org_id", table_name="workflow_trigger_states")
    op.drop_table("workflow_trigger_states")
    op.drop_index("uq_workflow_run_trigger_occurrence", table_name="workflow_runs")
    op.drop_column("workflow_runs", "trigger_occurrence_key")
    op.drop_column("workflow_runs", "trigger_type")
    op.drop_column("workflow_runs", "trigger_node_id")
    op.drop_column("workflow_runs", "graph_hash")
    op.drop_column("workflow_runs", "graph_snapshot")
