"""Add Google Drive OAuth connections for Customer Intelligence.

Revision ID: 0024_ci_drive
Revises: 0023_ci_calendar
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024_ci_drive"
down_revision = "0023_ci_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ci_drive_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False, server_default="google"),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("credentials_enc", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="disconnected"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "account_email", name="uq_ci_drive_org_account"),
    )
    op.create_index("ix_ci_drive_connections_org_id", "ci_drive_connections", ["org_id"])


def downgrade() -> None:
    op.drop_table("ci_drive_connections")
