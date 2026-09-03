from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class InboundMessage:
    channel: str
    sender_id: str
    sender_name: str
    conversation_id: str
    text: str
    raw: dict[str, Any]
    message_type: str = "text"
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TestResult:
    ok: bool
    message: str


class ChannelDriver(Protocol):
    """Protocol for messaging channel drivers.

    Each messaging platform (Telegram, Discord, Zalo, Slack, etc.)
    implements this protocol to provide a unified interface for
    sending messages and receiving webhooks.
    """

    async def send_message(
        self,
        recipient: str,
        content: str,
        **opts: Any,
    ) -> str:
        """Send a message to a recipient (chat/channel/user ID).

        Returns the external message ID.
        """
        ...

    async def parse_webhook(self, payload: dict[str, Any]) -> InboundMessage | None:
        """Parse a webhook payload into an InboundMessage.

        Returns None if the payload should be ignored (e.g., PING).
        """
        ...

    async def setup_webhook(self, url: str) -> None:
        """Configure the webhook URL on the platform side."""
        ...

    async def test_connection(self) -> TestResult:
        """Verify the connection credentials are valid."""
        ...
