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
                        (Agent.id == agent_id) & ((Agent.org_id == org_id) | (Agent.org_id.isnot(None)))
                    )
                )
            else:
                agent = None

            if agent is None:
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

            # Handle conversation reset command (/reset, /new, /clear)
            content_clean = (msg.content or "").strip().lower()
            if content_clean in {"/reset", "/new", "/clear"}:
                from app.services.channel_service import ChannelService

                service = ChannelService(db)
                session, _ = await service.ensure_conversation_session(
                    org_id=org_id,
                    connection=connection,
                    conversation_id=msg.conversation_id,
                    agent=agent,
                    sender_name=msg.sender_name,
                    force_new=True,
                )
                driver = build_channel_driver(connection)
                reset_text = "🔄 Đã làm mới phiên hội thoại thành công! Tôi đã sẵn sàng cho chủ đề mới."
                ext_id = await driver.send_message(
                    recipient=msg.conversation_id,
                    content=reset_text,
                )
                outbound = ChannelMessage(
                    org_id=org_id,
                    connection_id=connection_id,
                    direction="outbound",
                    external_message_id=ext_id or "",
                    conversation_id=msg.conversation_id,
                    message_type="text",
                    content=reset_text,
                    agent_id=agent.id,
                    metadata_json={"session_id": session.id, "command": content_clean},
                )
                db.add(outbound)
                await db.commit()
                return

            # Ensure durable conversation session mapping for multi-turn history & compaction
            from app.core.agent_loop import run_agent_loop
            from app.core.execution_policy import normalize_execution_policy
            from app.services.channel_service import ChannelService

            service = ChannelService(db)
            session, _ = await service.ensure_conversation_session(
                org_id=org_id,
                connection=connection,
                conversation_id=msg.conversation_id,
                agent=agent,
                sender_name=msg.sender_name,
                force_new=False,
            )

            # Tag inbound message with session_id
            inbound_meta = dict(msg.metadata_json or {})
            inbound_meta["session_id"] = session.id
            msg.metadata_json = inbound_meta
            db.add(msg)
            await db.commit()

            # Call agent loop with session context
            result = await run_agent_loop(
                agent=agent,
                message=msg.content,
                db=db,
                session_id=session.id,
                user_id=connection.created_by_user_id,
                user_role="user" if connection.created_by_user_id else None,
                record_stream=False,
                execution_policy=normalize_execution_policy(session.execution_policy),
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

            # Log outbound message with complete execution trace & session_id
            outbound = ChannelMessage(
                org_id=org_id,
                connection_id=connection_id,
                direction="outbound",
                external_message_id=external_id,
                conversation_id=msg.conversation_id,
                message_type="text",
                content=reply_text,
                agent_id=agent.id,
                metadata_json={
                    "session_id": session.id,
                    "tools": result.tool_calls,
                    "usage": result.usage,
                    "latency_ms": result.latency_ms,
                    "cost_usd": result.cost_usd,
                    "error": result.error,
                    "model": result.model or getattr(agent, "name", None),
                },
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
            try:
                connection = await db.get(ChannelConnection, connection_id)
                msg = await db.get(ChannelMessage, message_id)
                if connection and msg:
                    driver = build_channel_driver(connection)
                    err_msg = str(exc)
                    if "insufficient_quota" in err_msg or "Free quota exhausted" in err_msg:
                        user_friendly_error = "⚠️ Tài khoản AI provider đã hết quota miễn phí (Free quota exhausted). Vui lòng cấu hình API key hoặc nạp thêm token trên provider console."
                    elif "has no API key configured" in err_msg:
                        user_friendly_error = "⚠️ AI Provider chưa được cấu hình API key."
                    else:
                        user_friendly_error = f"⚠️ Không thể xử lý tin nhắn: {err_msg[:200]}"
                    ext_err_id = await driver.send_message(
                        recipient=msg.conversation_id,
                        content=user_friendly_error,
                    )
                    err_outbound = ChannelMessage(
                        org_id=org_id,
                        connection_id=connection_id,
                        direction="outbound",
                        external_message_id=ext_err_id or "",
                        conversation_id=msg.conversation_id,
                        message_type="error",
                        content=user_friendly_error,
                        metadata_json={"error": err_msg},
                    )
                    db.add(err_outbound)
                    await db.commit()
            except Exception:
                pass
