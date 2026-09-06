"""Add platform_config table for platform_admin-editable instance settings.

Revision ID: 0074_platform_config
Revises: 0073_approval_request_workflow_fields
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0074_platform_config"
down_revision: str | None = "0073_approval_request_workflow_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_config",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_platform_config_updated_by_user_id"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_config")
