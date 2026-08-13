"""Persist read-only email routing and user notifications."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0034_email_routing"
down_revision = "0033_gmail_push_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ci_emails", sa.Column("classification", sa.String(length=32), nullable=False, server_default="pending"))
    op.add_column("ci_emails", sa.Column("classification_confidence", sa.Float(), nullable=True))
    op.add_column("ci_emails", sa.Column("classification_reason", sa.Text(), nullable=True))
    op.add_column("ci_emails", sa.Column("routing_status", sa.String(length=32), nullable=False, server_default="pending"))
    op.create_index("ix_ci_emails_classification", "ci_emails", ["classification"])
    op.create_index("ix_ci_emails_routing_status", "ci_emails", ["routing_status"])
    op.create_table(
        "ci_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("email_id", sa.String(length=36), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=320), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["ci_emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", "email_id", "notification_type", name="uq_ci_notification_email_type"),
    )
    op.create_index("ix_ci_notifications_org_id", "ci_notifications", ["org_id"])
    op.create_index("ix_ci_notifications_user_id", "ci_notifications", ["user_id"])
    op.create_index("ix_ci_notifications_email_id", "ci_notifications", ["email_id"])


def downgrade() -> None:
    op.drop_index("ix_ci_notifications_email_id", table_name="ci_notifications")
    op.drop_index("ix_ci_notifications_user_id", table_name="ci_notifications")
    op.drop_index("ix_ci_notifications_org_id", table_name="ci_notifications")
    op.drop_table("ci_notifications")
    op.drop_index("ix_ci_emails_routing_status", table_name="ci_emails")
    op.drop_index("ix_ci_emails_classification", table_name="ci_emails")
    op.drop_column("ci_emails", "routing_status")
    op.drop_column("ci_emails", "classification_reason")
    op.drop_column("ci_emails", "classification_confidence")
    op.drop_column("ci_emails", "classification")
