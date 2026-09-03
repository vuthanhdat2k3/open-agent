from __future__ import annotations

import logging
from typing import Any

import httpx

from app.channels.driver import InboundMessage, TestResult

logger = logging.getLogger(__name__)


class TelegramDriver:
    """Telegram Bot API driver using direct HTTP calls.

    Uses the Telegram Bot API for sending messages and parsing webhooks.
    Does not require aiogram as a dependency - uses httpx for HTTP calls.
    """

    def __init__(self, bot_token: str, config: dict[str, Any]) -> None:
        self.token = bot_token
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(
        self,
        recipient: str,
        content: str,
        **opts: Any,
    ) -> str:
        """Send a message to a Telegram chat."""
        payload = {
            "chat_id": recipient,
            "text": content,
            "parse_mode": opts.get("parse_mode", "HTML"),
        }
        if opts.get("reply_to_message_id"):
            payload["reply_to_message_id"] = opts["reply_to_message_id"]
        if opts.get("disable_web_page_preview"):
            payload["disable_web_page_preview"] = opts["disable_web_page_preview"]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/sendMessage",
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error: {data}")
            return str(data["result"]["message_id"])

    async def parse_webhook(self, payload: dict[str, Any]) -> InboundMessage | None:
        """Parse a Telegram Update into an InboundMessage."""
        # Handle callback queries
        if "callback_query" in payload:
            cq = payload["callback_query"]
            message = cq.get("message", {})
            return InboundMessage(
                channel="telegram",
                sender_id=str(cq["from"]["id"]),
                sender_name=cq["from"].get("first_name", ""),
                conversation_id=str(message.get("chat", {}).get("id", "")),
                text=cq.get("data", ""),
                raw=payload,
                message_type="callback_query",
                metadata={"message_id": message.get("message_id")},
            )

        # Handle regular messages
        message = payload.get("message")
        if message is None:
            return None

        # Skip non-text messages for now
        if "text" not in message:
            return InboundMessage(
                channel="telegram",
                sender_id=str(message["from"]["id"]),
                sender_name=message["from"].get("first_name", ""),
                conversation_id=str(message["chat"]["id"]),
                text="",
                raw=payload,
                message_type="non_text",
                metadata={"message_type": next(
                    (k for k, v in message.items() if k not in ("from", "chat", "date", "message_id")),
                    "unknown"
                )},
            )

        return InboundMessage(
            channel="telegram",
            sender_id=str(message["from"]["id"]),
            sender_name=message["from"].get("first_name", ""),
            conversation_id=str(message["chat"]["id"]),
            text=message["text"],
            raw=payload,
            message_type="text",
            reply_to=str(message.get("reply_to_message", {}).get("message_id")) if message.get("reply_to_message") else None,
            metadata={
                "message_id": message.get("message_id"),
                "chat_type": message["chat"].get("type"),
            },
        )

    async def setup_webhook(self, url: str) -> None:
        """Set webhook URL on Telegram."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/setWebhook",
                json={"url": url},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Failed to set webhook: {data}")

    async def test_connection(self) -> TestResult:
        """Verify the bot token is valid."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/getMe",
                    timeout=10.0,
                )
                data = resp.json()
                if data.get("ok"):
                    bot_info = data["result"]
                    return TestResult(
                        ok=True,
                        message=f"@{bot_info.get('username', 'unknown')}",
                    )
                return TestResult(ok=False, message=data.get("description", "Unknown error"))
        except httpx.HTTPError as e:
            return TestResult(ok=False, message=f"HTTP error: {e}")
        except Exception as e:
            return TestResult(ok=False, message=str(e))
