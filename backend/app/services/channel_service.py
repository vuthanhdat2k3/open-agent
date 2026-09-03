from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.factory import build_channel_driver
from app.core.credential_secrets import decrypt_string, encrypt_string
from app.models.channel import ChannelConnection, ChannelMessage
from app.repositories.channel_repo import ChannelMessageRepository, ChannelRepository


class ChannelService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ChannelRepository(db)
        self.message_repo = ChannelMessageRepository(db)

    async def create_connection(
        self,
        org_id: str,
        provider: str,
        bot_token: str,
        config: dict[str, Any] | None = None,
        bot_username: str = "",
        owner_user_id: str | None = None,
    ) -> ChannelConnection:
        """Create a new channel connection.

        If `owner_user_id` is set, the connection is tied to that user
        (personal). Otherwise it is shared org-wide.
        """
        webhook_secret = secrets.token_hex(32)

        connection = ChannelConnection(
            org_id=org_id,
            created_by_user_id=owner_user_id,
            provider=provider,
            bot_token_enc=encrypt_string(bot_token),
            bot_username=bot_username,
            webhook_secret=webhook_secret,
            status="active",
            config=config or {},
        )
        return await self.repo.create(connection)

    async def list_connections(
        self,
        org_id: str,
        provider: str | None = None,
        owner_user_id: str | None = None,
    ) -> list[ChannelConnection]:
        """List channel connections.

        When `owner_user_id` is set, returns only personal connections owned
        by that user. When None, returns shared org-wide connections.
        """
        return await self.repo.list_by_provider(
            org_id, provider, owner_user_id=owner_user_id
        )

    async def list_connections_by_guild(
        self, guild_id: str
    ) -> list[ChannelConnection]:
        """Find connections by Discord guild ID (from config)."""
        from sqlalchemy import select

        res = await self.db.execute(
            select(ChannelConnection).where(
                ChannelConnection.provider == "discord",
                ChannelConnection.status == "active",
                ChannelConnection.config["guild_id"].as_string() == guild_id,
            )
        )
        return list(res.scalars().all())

    async def get_connection(
        self, org_id: str, connection_id: str
    ) -> ChannelConnection | None:
        """Get a channel connection by ID."""
        return await self.repo.get(org_id, connection_id)

    async def update_connection(
        self,
        org_id: str,
        connection_id: str,
        **updates: Any,
    ) -> ChannelConnection | None:
        """Update a channel connection."""
        conn = await self.repo.get(org_id, connection_id)
        if conn is None:
            return None

        # Encrypt bot_token if being updated
        if "bot_token" in updates:
            updates["bot_token_enc"] = encrypt_string(updates.pop("bot_token"))

        await self.repo.update(conn, updates)
        return await self.repo.get(org_id, connection_id)

    async def delete_connection(
        self, org_id: str, connection_id: str
    ) -> bool:
        """Delete a channel connection."""
        return await self.repo.delete(org_id, connection_id)

    async def test_connection(
        self, org_id: str, connection_id: str
    ) -> dict[str, Any]:
        """Test a channel connection."""
        conn = await self.repo.get(org_id, connection_id)
        if conn is None:
            return {"ok": False, "message": "Connection not found"}

        try:
            driver = build_channel_driver(conn)
            result = await driver.test_connection()
            # Update status based on test result
            conn.status = "active" if result.ok else "error"
            self.db.add(conn)
            await self.db.commit()
            return {"ok": result.ok, "message": result.message}
        except Exception as e:
            conn.status = "error"
            self.db.add(conn)
            await self.db.commit()
            return {"ok": False, "message": str(e)}

    async def get_webhook_secret(
        self, org_id: str, connection_id: str
    ) -> str | None:
        """Get the webhook secret for a connection."""
        conn = await self.repo.get(org_id, connection_id)
        return conn.webhook_secret if conn else None

    async def find_connection_by_webhook_secret(
        self, provider: str, webhook_secret: str
    ) -> ChannelConnection | None:
        """Find a connection by provider and webhook secret."""
        from sqlalchemy import select

        res = await self.db.execute(
            select(ChannelConnection).where(
                ChannelConnection.provider == provider,
                ChannelConnection.webhook_secret == webhook_secret,
                ChannelConnection.status == "active",
            )
        )
        return res.scalar_one_or_none()

    async def handle_inbound_message(
        self,
        org_id: str,
        connection_id: str,
        message: Any,
    ) -> ChannelMessage:
        """Store an inbound message from a channel."""
        db_message = ChannelMessage(
            org_id=org_id,
            connection_id=connection_id,
            direction="inbound",
            external_message_id=str(message.metadata.get("message_id", "")),
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            conversation_id=message.conversation_id,
            message_type=message.message_type,
            content=message.text,
            metadata_json=message.raw,
        )
        return await self.message_repo.create(db_message)

    async def handle_outbound_message(
        self,
        org_id: str,
        connection_id: str,
        conversation_id: str,
        content: str,
        agent_id: str | None = None,
        external_message_id: str = "",
    ) -> ChannelMessage:
        """Store an outbound message sent to a channel."""
        db_message = ChannelMessage(
            org_id=org_id,
            connection_id=connection_id,
            direction="outbound",
            external_message_id=external_message_id,
            conversation_id=conversation_id,
            message_type="text",
            content=content,
            agent_id=agent_id,
        )
        return await self.message_repo.create(db_message)

    async def get_decrypted_token(self, connection: ChannelConnection) -> str:
        """Get the decrypted bot token for a connection."""
        return decrypt_string(connection.bot_token_enc)

    async def list_messages(
        self,
        org_id: str,
        connection_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChannelMessage]:
        """List messages for a connection."""
        return await self.message_repo.list_by_connection(
            org_id, connection_id, limit, offset
        )
