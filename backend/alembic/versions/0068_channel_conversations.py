"""Add channel_conversations table for persistent channel session mapping.

Revision ID: 0068_channel_conversations
Revises: 0067_channel_owner
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0068_channel_conversations"
down_revision: str | None = "0067_channel_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE", name="fk_channel_conversations_org_id"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("channel_connections.id", ondelete="CASCADE", name="fk_channel_conversations_connection_id"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE", name="fk_channel_conversations_session_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(length=36),
            sa.ForeignKey("agents.id", ondelete="CASCADE", name="fk_channel_conversations_agent_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("connection_id", "conversation_id", name="uq_channel_conv_connection_conversation"),
    )
    op.create_index("ix_channel_conversations_org_id", "channel_conversations", ["org_id"])
    op.create_index("ix_channel_conversations_connection_id", "channel_conversations", ["connection_id"])
    op.create_index("ix_channel_conversations_conversation_id", "channel_conversations", ["conversation_id"])
    op.create_index("ix_channel_conversations_session_id", "channel_conversations", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_conversations_session_id", table_name="channel_conversations")
    op.drop_index("ix_channel_conversations_conversation_id", table_name="channel_conversations")
    op.drop_index("ix_channel_conversations_connection_id", table_name="channel_conversations")
    op.drop_index("ix_channel_conversations_org_id", table_name="channel_conversations")
    op.drop_table("channel_conversations")
