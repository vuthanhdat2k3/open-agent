from __future__ import annotations

import asyncio
from typing import Any

try:
    import nextcord
except ImportError:
    nextcord = None
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
        self._clients: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._shutdown: bool = False


    async def start(self) -> None:
        """Start gateway clients for all active Discord connections."""
        if nextcord is None:
            logger.info("nextcord_not_installed_skipping_discord_gateway")
            return

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
        if nextcord is None:
            logger.info("nextcord_not_installed_skipping_discord_bot", connection_id=conn.id)
            return

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
            try:
                await client.change_presence(
                    status=nextcord.Status.online,
                    activity=nextcord.Activity(
                        type=nextcord.ActivityType.listening,
                        name="tin nhắn / @open-agent",
                    ),
                )
            except Exception as pe:
                logger.warning("discord_change_presence_failed", error=str(pe))

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

    async def _run_client(self, client: Any, token: str, conn_id: str) -> None:
        """Run the Discord client with automatic reconnect."""
        backoff = 5.0
        while not self._shutdown and conn_id in self._clients:
            try:
                await client.start(token)
                break
            except nextcord.LoginFailure:
                logger.error("discord_login_failed", connection_id=conn_id)
                await self._mark_error(conn_id)
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("discord_client_error_reconnecting", connection_id=conn_id, error=str(e))
                if self._shutdown or conn_id not in self._clients:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 60.0)
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
        self._shutdown = True
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


# Singleton instance for Discord
_discord_manager: DiscordBotManager | None = None


def get_discord_manager() -> DiscordBotManager:
    global _discord_manager
    if _discord_manager is None:
        _discord_manager = DiscordBotManager()
    return _discord_manager


class TelegramBotManager:
    """Manages Telegram bot long-polling runners to receive messages in real time.

    For each active Telegram connection, maintains a background polling task
    calling getUpdates with long polling timeout. This eliminates the requirement
    for public HTTPS domains or webhooks in local development and standard deployments.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._shutdown: bool = False

    async def start(self) -> None:
        """Start long-polling runners for all active Telegram connections."""
        async with SessionLocal() as db:
            from sqlalchemy import select

            res = await db.execute(
                select(ChannelConnection).where(
                    ChannelConnection.provider == "telegram",
                    ChannelConnection.status == "active",
                )
            )
            connections = list(res.scalars().all())

        for conn in connections:
            await self.add_bot(conn)

    async def add_bot(self, conn: ChannelConnection) -> None:
        """Add and start a long-polling runner for a Telegram bot."""
        if conn.id in self._tasks:
            logger.info("telegram_bot_already_running", connection_id=conn.id)
            return

        try:
            token = decrypt_string(conn.bot_token_enc)
        except Exception as e:
            logger.error("telegram_bot_token_decrypt_failed", connection_id=conn.id, error=str(e))
            return

        task = asyncio.create_task(self._run_bot(conn, token))
        self._tasks[conn.id] = task
        logger.info("telegram_bot_started", connection_id=conn.id, username=conn.bot_username)

    async def _run_bot(self, conn: ChannelConnection, token: str) -> None:
        """Long-poll Telegram API for updates and dispatch them to the message queue."""
        import httpx

        from app.channels.factory import build_channel_driver

        base_url = f"https://api.telegram.org/bot{token}"
        offset = 0
        backoff = 2.0

        # Check and clear webhook if set, allowing getUpdates long-polling
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{base_url}/getWebhookInfo")
                if resp.status_code == 200:
                    info = resp.json().get("result", {})
                    if info.get("url"):
                        logger.info(
                            "telegram_clearing_webhook_for_polling",
                            connection_id=conn.id,
                            webhook_url=info.get("url"),
                        )
                        await client.post(f"{base_url}/deleteWebhook")
        except Exception as e:
            logger.warning("telegram_check_webhook_failed", connection_id=conn.id, error=str(e))

        driver = build_channel_driver(conn)

        while not self._shutdown and conn.id in self._tasks:
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.get(
                        f"{base_url}/getUpdates",
                        params={"offset": offset, "timeout": 25},
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        backoff = 2.0
                        for update in updates:
                            update_id = update["update_id"]
                            offset = update_id + 1
                            await self._process_update(conn, driver, update)
                    elif resp.status_code == 409:
                        # Webhook or another poll instance conflict
                        logger.warning("telegram_poll_conflict", connection_id=conn.id)
                        await asyncio.sleep(5.0)
                    else:
                        logger.warning(
                            "telegram_poll_http_error",
                            connection_id=conn.id,
                            status=resp.status_code,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 1.5, 30.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._shutdown or conn.id not in self._tasks:
                    break
                logger.warning("telegram_poll_exception", connection_id=conn.id, error=str(e))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)

        self._tasks.pop(conn.id, None)

    async def _process_update(
        self,
        conn: ChannelConnection,
        driver: Any,
        update: dict[str, Any],
    ) -> None:
        """Parse an update and enqueue it for processing."""
        try:
            inbound = await driver.parse_webhook(update)
            if not inbound:
                return

            # Trigger typing indicator immediately
            try:
                await driver.trigger_typing(inbound.conversation_id)
            except Exception:
                pass

            from arq import create_pool

            from app.core.workflow.queue import _redis_settings
            from app.db.session import SessionLocal
            from app.services.channel_service import ChannelService

            async with SessionLocal() as db:
                service = ChannelService(db)
                db_msg = await service.handle_inbound_message(conn.org_id, conn.id, inbound)
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
                await pool.aclose()

        except Exception as e:
            logger.error("telegram_update_dispatch_failed", connection_id=conn.id, error=str(e))

    async def remove_bot(self, conn_id: str) -> None:
        """Stop and remove a Telegram bot runner."""
        task = self._tasks.pop(conn_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def shutdown(self) -> None:
        """Stop all Telegram bot runners."""
        self._shutdown = True
        for conn_id in list(self._tasks.keys()):
            await self.remove_bot(conn_id)


# Singleton instance for Telegram
_telegram_manager: TelegramBotManager | None = None


def get_telegram_manager() -> TelegramBotManager:
    global _telegram_manager
    if _telegram_manager is None:
        _telegram_manager = TelegramBotManager()
    return _telegram_manager

