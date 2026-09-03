from __future__ import annotations

import asyncio

import nextcord
import structlog

from app.core.credential_secrets import decrypt_string
from app.db.session import SessionLocal
from app.models.channel import ChannelConnection

logger = structlog.get_logger(__name__)


class DiscordBotManager:
    """Manages Discord bot gateway connections to keep bots online.

    Each active Discord connection spawns a gateway client that maintains
    a WebSocket connection to Discord. This makes the bot appear online
    in Discord servers.
    """

    def __init__(self) -> None:
        self._clients: dict[str, nextcord.Client] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Start gateway clients for all active Discord connections."""
        async with SessionLocal() as db:
            from sqlalchemy import select
            res = await db.execute(
                select(ChannelConnection).where(
                    ChannelConnection.provider == "discord",
                    ChannelConnection.status == "active",
                )
            )
            connections = list(res.scalars().all())

        for conn in connections:
            await self.add_bot(conn)

    async def add_bot(self, conn: ChannelConnection) -> None:
        """Add and start a new Discord bot gateway client."""
        if conn.id in self._clients:
            logger.info("bot_already_running", connection_id=conn.id)
            return

        try:
            token = decrypt_string(conn.bot_token_enc)
        except Exception as e:
            logger.error("bot_token_decrypt_failed", connection_id=conn.id, error=str(e))
            return

        intents = nextcord.Intents.default()
        client = nextcord.Client(intents=intents)

        @client.event
        async def on_ready() -> None:
            logger.info(
                "discord_bot_online",
                connection_id=conn.id,
                bot_name=str(client.user),
                guilds=len(client.guilds),
            )

        @client.event
        async def on_message(message: nextcord.Message) -> None:
            # Ignore messages sent by any bot to avoid infinite loops
            if message.author.bot:
                return

            is_dm = isinstance(message.channel, nextcord.DMChannel)
            is_mentioned = bool(
                client.user
                and (
                    client.user in message.mentions
                    or f"<@{client.user.id}>" in (message.content or "")
                    or f"<@!{client.user.id}>" in (message.content or "")
                )
            )

            # In server channels, only respond when directly mentioned or in DMs
            if not is_dm and not is_mentioned:
                return

            text = message.clean_content or message.content or ""
            if client.user:
                text = (
                    text.replace(f"@{client.user.name}", "")
                    .replace(f"@{client.user.display_name}", "")
                    .replace(f"<@{client.user.id}>", "")
                    .replace(f"<@!{client.user.id}>", "")
                    .strip()
                )

            if not text:
                text = "Xin chào"

            logger.info(
                "discord_message_received",
                connection_id=conn.id,
                author=str(message.author),
                channel_id=str(message.channel.id),
                content=text[:60],
            )

            try:
                # Trigger typing indicator so user sees bot is working
                try:
                    await message.channel.trigger_typing()
                except Exception:
                    pass

                from arq import create_pool
                from app.channels.driver import InboundMessage
                from app.core.channels.jobs import process_channel_message
                from app.core.workflow.queue import _redis_settings
                from app.db.session import SessionLocal
                from app.services.channel_service import ChannelService

                inbound = InboundMessage(
                    channel="discord",
                    sender_id=str(message.author.id),
                    sender_name=str(getattr(message.author, "display_name", message.author.name)),
                    conversation_id=str(message.channel.id),
                    text=text,
                    raw={
                        "id": str(message.id),
                        "channel_id": str(message.channel.id),
                        "guild_id": str(message.guild.id) if message.guild else None,
                        "author_id": str(message.author.id),
                    },
                    message_type="text",
                    metadata={
                        "message_id": str(message.id),
                        "guild_id": str(message.guild.id) if message.guild else "",
                    },
                )

                async with SessionLocal() as db:
                    service = ChannelService(db)
                    db_msg = await service.handle_inbound_message(
                        conn.org_id, conn.id, inbound
                    )
                    await db.commit()
                    msg_id = str(db_msg.id)

                pool = await create_pool(_redis_settings())
                try:
                    await pool.enqueue_job(
                        "process_channel_message",
                        str(conn.org_id),
                        str(conn.id),
                        msg_id,
                    )
                finally:
                    await pool.close()

            except Exception as e:
                logger.error("discord_message_dispatch_failed", connection_id=conn.id, error=str(e))

        @client.event
        async def on_error(event: str, *args, **kwargs) -> None:
            logger.error("discord_bot_error", connection_id=conn.id, event=event)

        task = asyncio.create_task(self._run_client(client, token, conn.id))
        self._clients[conn.id] = client
        self._tasks[conn.id] = task

    async def _run_client(self, client: nextcord.Client, token: str, conn_id: str) -> None:
        """Run the Discord client with automatic reconnect."""
        try:
            await client.start(token)
        except nextcord.LoginFailure:
            logger.error("discord_login_failed", connection_id=conn_id)
            await self._mark_error(conn_id)
        except Exception as e:
            logger.error("discord_client_error", connection_id=conn_id, error=str(e))
        finally:
            self._clients.pop(conn_id, None)
            self._tasks.pop(conn_id, None)

    async def remove_bot(self, conn_id: str) -> None:
        """Disconnect and remove a Discord bot."""
        client = self._clients.pop(conn_id, None)
        task = self._tasks.pop(conn_id, None)
        if client and not client.is_closed():
            await client.close()
        if task and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        """Disconnect all Discord bots."""
        for conn_id in list(self._clients.keys()):
            await self.remove_bot(conn_id)

    async def _mark_error(self, conn_id: str) -> None:
        """Mark a connection as error in the database."""
        try:
            async with SessionLocal() as db:
                conn = await db.get(ChannelConnection, conn_id)
                if conn:
                    conn.status = "error"
                    db.add(conn)
                    await db.commit()
        except Exception as e:
            logger.error("mark_error_failed", connection_id=conn_id, error=str(e))


# Singleton instance
_manager: DiscordBotManager | None = None


def get_discord_manager() -> DiscordBotManager:
    global _manager
    if _manager is None:
        _manager = DiscordBotManager()
    return _manager
