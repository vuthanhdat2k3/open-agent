"""Add Gmail push notification and watch checkpoint fields."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0033_gmail_push_ingestion"
down_revision = "0032_durable_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ci_connections", sa.Column("gmail_history_id", sa.String(length=64), nullable=True))
    op.add_column("ci_connections", sa.Column("watch_expiration_at", sa.DateTime(), nullable=True))
    op.add_column("ci_connections", sa.Column("watch_resource_name", sa.String(length=512), nullable=True))
    op.create_table(
        "ci_gmail_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("history_id", sa.String(length=64), nullable=False),
        sa.Column("provider_notification_id", sa.String(length=256), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="received"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["ci_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "history_id", name="uq_ci_gmail_notification_history"),
    )
    op.create_index("ix_ci_gmail_notifications_org_id", "ci_gmail_notifications", ["org_id"])
    op.create_index("ix_ci_gmail_notifications_connection_id", "ci_gmail_notifications", ["connection_id"])


def downgrade() -> None:
    op.drop_index("ix_ci_gmail_notifications_connection_id", table_name="ci_gmail_notifications")
    op.drop_index("ix_ci_gmail_notifications_org_id", table_name="ci_gmail_notifications")
    op.drop_table("ci_gmail_notifications")
    op.drop_column("ci_connections", "watch_resource_name")
    op.drop_column("ci_connections", "watch_expiration_at")
    op.drop_column("ci_connections", "gmail_history_id")
