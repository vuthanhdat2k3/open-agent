"""Add created_by_user_id to channel_connections for personal/user-owned connections.

Revision ID: 0067_channel_owner
Revises: 0066_channel_connections
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0067_channel_owner"
down_revision: str | None = "0066_channel_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("channel_connections") as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_by_user_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_channel_connections_created_by_user_id"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_channel_connections_created_by_user_id", ["created_by_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("channel_connections") as batch_op:
        batch_op.drop_index("ix_channel_connections_created_by_user_id")
        batch_op.drop_column("created_by_user_id")
