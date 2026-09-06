"""Add title/instructions/approver_user_ids to approval_requests.

Backs the workflow `approval` node's title/instructions/approver_user_ids
config fields, which the engine previously accepted but never persisted or
enforced.

Revision ID: 0073_approval_request_workflow_fields
Revises: 0072_notifications
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_approval_request_workflow_fields"
down_revision: str | None = "0072_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("approval_requests", sa.Column("instructions", sa.Text(), nullable=False, server_default=""))
    op.add_column("approval_requests", sa.Column("approver_user_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("approval_requests", "approver_user_ids")
    op.drop_column("approval_requests", "instructions")
    op.drop_column("approval_requests", "title")
