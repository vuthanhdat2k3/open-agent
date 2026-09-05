from __future__ import annotations

from sqlalchemy import select

from app.channels.factory import build_channel_driver
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.models.channel import ChannelConnection


async def _send_channel_message(args: dict, ctx: ToolContext) -> str:
    """Send a message via a connected messaging channel (Telegram, Discord)."""
    channel_id = args.get("channel_id", "")
    recipient = args.get("recipient", "")
    content = args.get("content", "")

    if not channel_id:
        return "error: missing 'channel_id'"
    if not recipient:
        return "error: missing 'recipient'"
    if not content:
        return "error: missing 'content'"

    if not ctx.db or not ctx.org_id:
        return "error: database and org context required"

    # Load connection
    res = await ctx.db.execute(
        select(ChannelConnection).where(
            ChannelConnection.id == channel_id,
            ChannelConnection.org_id == ctx.org_id,
            ChannelConnection.status == "active",
        )
    )
    connection = res.scalar_one_or_none()
    if connection is None:
        return f"error: channel connection '{channel_id}' not found or inactive"

    try:
        driver = build_channel_driver(connection)
        external_id = await driver.send_message(
            recipient=recipient,
            content=content,
        )
        return f"Message sent via {connection.provider} (id: {external_id})"
    except Exception as e:
        return f"error sending message: {e}"


async def _list_channel_connections(args: dict, ctx: ToolContext) -> str:
    """List available channel connections for the current org."""
    if not ctx.db or not ctx.org_id:
        return "error: database and org context required"

    res = await ctx.db.execute(
        select(ChannelConnection).where(
            ChannelConnection.org_id == ctx.org_id,
            ChannelConnection.status == "active",
        ).order_by(ChannelConnection.created_at.desc())
    )
    connections = list(res.scalars().all())

    if not connections:
        return "No active channel connections configured."

    lines = []
    for c in connections:
        lines.append(f"- {c.id}: {c.provider} (@{c.bot_username or 'unknown'})")
    return "\n".join(lines)


def register_channel_tools() -> None:
    """Register channel messaging tools."""
    register(ToolSpec(
        name="send_channel_message",
        description=(
            "Send a message to a user via a connected messaging channel "
            "(Telegram, Discord). Requires channel_id, recipient (chat/user ID), "
            "and content."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel connection to use",
                },
                "recipient": {
                    "type": "string",
                    "description": "Recipient chat ID (Telegram) or channel ID (Discord)",
                },
                "content": {
                    "type": "string",
                    "description": "Message content to send",
                },
            },
            "required": ["channel_id", "recipient", "content"],
        },
        run=_send_channel_message,
        risk_tier=RiskTier.network,
        requires_approval=True,
    ))

    register(ToolSpec(
        name="list_channel_connections",
        description="List all active messaging channel connections for the organization.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        run=_list_channel_connections,
        risk_tier=RiskTier.safe,
    ))
