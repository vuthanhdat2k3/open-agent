from __future__ import annotations

import logging
from typing import Any

import httpx

from app.channels.driver import InboundMessage, TestResult

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordDriver:
    """Discord Bot API driver using direct HTTP calls.

    Uses the Discord API for sending messages and parsing interaction webhooks.
    Supports both bot token auth and webhook URL sending.
    """

    def __init__(self, bot_token: str, config: dict[str, Any]) -> None:
        self.token = bot_token
        self.config = config
        self.headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }

    async def send_message(
        self,
        recipient: str,
        content: str,
        **opts: Any,
    ) -> str:
        """Send a message to a Discord channel."""
        payload: dict[str, Any] = {
            "content": content,
        }
        if opts.get("embeds"):
            payload["embeds"] = opts["embeds"]
        if opts.get("components"):
            payload["components"] = opts["components"]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{DISCORD_API_BASE}/channels/{recipient}/messages",
                json=payload,
                headers=self.headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data["id"])

    async def parse_webhook(self, payload: dict[str, Any]) -> InboundMessage | None:
        """Parse a Discord interaction payload into an InboundMessage.

        Discord sends interaction payloads for slash commands and component interactions.
        """
        interaction_type = payload.get("type")

        # PING - Discord verifying the endpoint
        if interaction_type == 1:
            return None

        # PONG or other non-message types
        if interaction_type != 2 and interaction_type != 3:
            return None

        member = payload.get("member", {})
        user = member.get("user", payload.get("user", {}))

        # Type 2 = Slash command (APPLICATION_COMMAND)
        if interaction_type == 2:
            data = payload.get("data", {})
            options = data.get("options", [])
            # Build text from command and options
            text = f"/{data.get('name', '')}"
            if options:
                text += " " + " ".join(
                    str(opt.get("value", "")) for opt in options
                )

            return InboundMessage(
                channel="discord",
                sender_id=user.get("id", ""),
                sender_name=user.get("username", ""),
                conversation_id=payload.get("channel_id", data.get("channel_id", "")),
                text=text,
                raw=payload,
                message_type="slash_command",
                metadata={
                    "interaction_id": payload.get("id"),
                    "guild_id": payload.get("guild_id"),
                    "command_id": data.get("id"),
                    "command_name": data.get("name"),
                },
            )

        # Type 3 = Component interaction (MESSAGE_COMPONENT)
        if interaction_type == 3:
            data = payload.get("data", {})
            message = payload.get("message", {})
            return InboundMessage(
                channel="discord",
                sender_id=user.get("id", ""),
                sender_name=user.get("username", ""),
                conversation_id=payload.get("channel_id", ""),
                text=data.get("custom_id", ""),
                raw=payload,
                message_type="component_interaction",
                metadata={
                    "interaction_id": payload.get("id"),
                    "custom_id": data.get("custom_id"),
                    "component_type": data.get("component_type"),
                    "message_id": message.get("id"),
                },
            )

        return None

    async def setup_webhook(self, url: str) -> None:
        """Discord interactions endpoint URL is set in Developer Portal.

        This method is a no-op since Discord requires setting the
        interactions endpoint URL via the Discord Developer Portal.
        """
        logger.info(
            "Discord interactions endpoint URL must be set in the Discord Developer Portal: %s",
            url,
        )

    async def test_connection(self) -> TestResult:
        """Verify the bot token is valid."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{DISCORD_API_BASE}/applications/@me",
                    headers=self.headers,
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return TestResult(
                        ok=True,
                        message=data.get("name", "Unknown"),
                    )
                return TestResult(
                    ok=False,
                    message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except httpx.HTTPError as e:
            return TestResult(ok=False, message=f"HTTP error: {e}")
        except Exception as e:
            return TestResult(ok=False, message=str(e))
