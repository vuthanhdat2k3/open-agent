"""Ops/Reliability agent schema: Agent.visibility, Session.workspace_override_path, ops_findings table.

Revision ID: 0071_ops_agent_schema
Revises: 0070_widen_approval_idempotency_key
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0071_ops_agent_schema"
down_revision: str | None = "0070_widen_approval_idempotency_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.add_column(
            sa.Column("visibility", sa.String(length=16), nullable=False, server_default="all")
        )
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column("workspace_override_path", sa.String(length=512), nullable=True)
        )
    op.create_table(
        "ops_findings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="reported"),
        sa.Column("pr_url", sa.String(length=512), nullable=True),
        sa.Column("related_run_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ops_findings_org_id", "ops_findings", ["org_id"])
    op.create_index("ix_ops_findings_severity", "ops_findings", ["severity"])
    op.create_index("ix_ops_findings_status", "ops_findings", ["status"])
    op.create_index("ix_ops_findings_related_run_id", "ops_findings", ["related_run_id"])
    op.create_index("ix_ops_findings_created_at", "ops_findings", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ops_findings_created_at", table_name="ops_findings")
    op.drop_index("ix_ops_findings_related_run_id", table_name="ops_findings")
    op.drop_index("ix_ops_findings_status", table_name="ops_findings")
    op.drop_index("ix_ops_findings_severity", table_name="ops_findings")
    op.drop_index("ix_ops_findings_org_id", table_name="ops_findings")
    op.drop_table("ops_findings")
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("workspace_override_path")
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("visibility")
