"""Add separate calendar OAuth connections for Customer Intelligence.

Revision ID: 0023_customer_intelligence_calendar
Revises: 0022_customer_intelligence
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023_ci_calendar"
down_revision = "0022_customer_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ci_calendar_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("credentials_enc", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="disconnected"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "provider", "account_email", name="uq_ci_calendar_org_provider_account"),
    )
    op.create_index("ix_ci_calendar_connections_org_id", "ci_calendar_connections", ["org_id"])
    with op.batch_alter_table("ci_cases") as batch_op:
        batch_op.add_column(
            sa.Column(
                "calendar_connection_id",
                sa.String(length=36),
                sa.ForeignKey("ci_calendar_connections.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_ci_cases_calendar_connection_id", ["calendar_connection_id"])


def downgrade() -> None:
    with op.batch_alter_table("ci_cases") as batch_op:
        batch_op.drop_index("ix_ci_cases_calendar_connection_id")
        batch_op.drop_column("calendar_connection_id")
    op.drop_table("ci_calendar_connections")
