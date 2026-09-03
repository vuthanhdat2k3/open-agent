"""Add channel_connections and channel_messages tables for messaging integrations.

Revision ID: 0066_channel_connections
Revises: 0065_workflow_template_scoping
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_channel_connections"
down_revision: str | None = "0065_workflow_template_scoping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE", name="fk_channel_connections_org_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("bot_token_enc", sa.Text(), nullable=False),
        sa.Column("bot_username", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("webhook_secret", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "provider", "bot_username", name="uq_channel_org_provider_username"),
    )
    op.create_index("ix_channel_connections_org_id", "channel_connections", ["org_id"])
    op.create_index("ix_channel_connections_provider", "channel_connections", ["provider"])

    op.create_table(
        "channel_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE", name="fk_channel_messages_org_id"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("channel_connections.id", ondelete="CASCADE", name="fk_channel_messages_connection_id"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("external_message_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("sender_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("sender_name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("conversation_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("message_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_channel_messages_org_id", "channel_messages", ["org_id"])
    op.create_index("ix_channel_messages_connection_id", "channel_messages", ["connection_id"])
    op.create_index("ix_channel_messages_conversation_id", "channel_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_messages_conversation_id", table_name="channel_messages")
    op.drop_index("ix_channel_messages_connection_id", table_name="channel_messages")
    op.drop_index("ix_channel_messages_org_id", table_name="channel_messages")
    op.drop_table("channel_messages")

    op.drop_index("ix_channel_connections_provider", table_name="channel_connections")
    op.drop_index("ix_channel_connections_org_id", table_name="channel_connections")
    op.drop_table("channel_connections")
