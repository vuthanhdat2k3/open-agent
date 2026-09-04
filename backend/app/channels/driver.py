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


def split_message(
    content: str,
    max_length: int = 1900,
    fallback: str = "(Không có nội dung phản hồi)",
) -> list[str]:
    """Split a message into chunks within max_length, preserving natural boundaries.

    Ensures no chunk exceeds max_length to avoid platform limits (e.g. Discord 2000 chars,
    Telegram 4096 chars). Empty/whitespace content returns the fallback text.
    """
    if not content or not content.strip():
        return [fallback]

    if len(content) <= max_length:
        return [content]

    chunks: list[str] = []
    remaining = content.strip()

    while len(remaining) > max_length:
        candidate = remaining[:max_length]

        # 1. Double newline (paragraph break)
        split_pos = candidate.rfind("\n\n")
        if split_pos >= max_length // 2:
            chunk = remaining[:split_pos].rstrip()
            remaining = remaining[split_pos + 2 :].lstrip("\r\n")
            if chunk:
                chunks.append(chunk)
            continue

        # 2. Single newline (line break)
        split_pos = candidate.rfind("\n")
        if split_pos >= max_length // 3:
            chunk = remaining[:split_pos].rstrip()
            remaining = remaining[split_pos + 1 :].lstrip("\r\n")
            if chunk:
                chunks.append(chunk)
            continue

        # 3. Space (word boundary)
        split_pos = candidate.rfind(" ")
        if split_pos >= max_length // 3:
            chunk = remaining[:split_pos].rstrip()
            remaining = remaining[split_pos + 1 :].lstrip(" ")
            if chunk:
                chunks.append(chunk)
            continue

        # 4. Hard cut
        chunks.append(candidate)
        remaining = remaining[max_length:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks or [fallback]

