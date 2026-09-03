from __future__ import annotations

import structlog
from sqlalchemy import select

from app.channels.factory import build_channel_driver
from app.db.session import SessionLocal
from app.models.agent import Agent
from app.models.channel import ChannelConnection, ChannelMessage

logger = structlog.get_logger(__name__)


async def process_channel_message(
    ctx: dict,
    org_id: str,
    connection_id: str,
    message_id: str,
) -> None:
    """Process an inbound channel message: call agent and reply.

    This is an ARQ background job that:
    1. Loads the inbound message
    2. Finds the target agent (from config or org default)
    3. Calls the agent loop
    4. Sends the reply back via the channel
    """
    async with SessionLocal() as db:
        try:
            # Load inbound message
            msg = await db.get(ChannelMessage, message_id)
            if msg is None or msg.direction != "inbound":
                await logger.ainfo("channel_message_skip", message_id=message_id, reason="not_found_or_not_inbound")
                return

            # Load connection
            connection = await db.get(ChannelConnection, connection_id)
            if connection is None or connection.status != "active":
                await logger.ainfo("channel_message_skip", connection_id=connection_id, reason="connection_inactive")
                return

            # Find target agent
            agent_id = connection.config.get("default_agent_id") if connection.config else None

            if agent_id:
                agent = await db.scalar(
                    select(Agent).where(
                        Agent.id == agent_id,
                        Agent.org_id == org_id,
                    )
                )
            else:
                # Fallback: use org's orchestrator agent
                agent = await db.scalar(
                    select(Agent).where(
                        Agent.org_id == org_id,
                        Agent.kind == "orchestrator",
                    ).order_by(Agent.created_at.asc())
                )

            if agent is None:
                await logger.aerror("channel_message_no_agent", org_id=org_id, connection_id=connection_id)
                return

            await logger.ainfo(
                "channel_message_processing",
                org_id=org_id,
                connection_id=connection_id,
                agent_id=agent.id,
                message=msg.content[:100],
            )

            # Call agent loop
            from app.core.agent_loop import run_agent_loop

            result = await run_agent_loop(
                agent=agent,
                message=msg.content,
                db=db,
                user_id=None,  # System-triggered
                user_role=None,
                record_stream=False,
            )

            if result.error:
                await logger.aerror(
                    "channel_message_agent_error",
                    agent_id=agent.id,
                    error=result.error,
                )
                reply_text = f"Xin lỗi, đã có lỗi xảy ra: {result.error}"
            else:
                reply_text = result.content

            # Send reply via channel
            driver = build_channel_driver(connection)
            external_id = await driver.send_message(
                recipient=msg.conversation_id,
                content=reply_text,
            )

            # Log outbound message
            outbound = ChannelMessage(
                org_id=org_id,
                connection_id=connection_id,
                direction="outbound",
                external_message_id=external_id,
                conversation_id=msg.conversation_id,
                message_type="text",
                content=reply_text,
                agent_id=agent.id,
            )
            db.add(outbound)
            await db.commit()

            await logger.ainfo(
                "channel_message_replied",
                org_id=org_id,
                connection_id=connection_id,
                agent_id=agent.id,
            )

        except Exception as exc:
            await logger.aerror(
                "channel_message_failed",
                org_id=org_id,
                connection_id=connection_id,
                message_id=message_id,
                error=str(exc),
            )
            await db.rollback()
