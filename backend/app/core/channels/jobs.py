from __future__ import annotations

import asyncio
import time
from typing import Any

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

            # Build channel driver
            driver = build_channel_driver(connection)

            # Continuous typing heartbeat to keep Discord/Telegram typing indicator active
            stop_typing = asyncio.Event()

            async def _typing_heartbeat() -> None:
                while not stop_typing.is_set():
                    try:
                        await driver.trigger_typing(msg.conversation_id)
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(stop_typing.wait(), timeout=6.0)
                    except TimeoutError:
                        pass

            typing_task = asyncio.create_task(_typing_heartbeat())

            # Progressive streaming state: completely non-blocking background flusher
            streamed_msg_id: str | None = None
            accumulated_tokens: list[str] = []
            status_hint: str | None = None
            flusher_stop = asyncio.Event()
            flusher_dirty = asyncio.Event()
            flusher_lock = asyncio.Lock()
            # Telegram rate limit: ~1 edit per second; Discord ~0.8s
            min_edit_interval = 1.2 if connection.provider == "telegram" else 0.8
            last_edit_ts = 0.0

            async def _flusher_loop() -> None:
                nonlocal streamed_msg_id, last_edit_ts
                while not flusher_stop.is_set():
                    try:
                        await asyncio.wait_for(flusher_dirty.wait(), timeout=min_edit_interval)
                        flusher_dirty.clear()
                    except TimeoutError:
                        pass

                    if flusher_stop.is_set():
                        break

                    now = time.monotonic()
                    elapsed = now - last_edit_ts
                    if elapsed < min_edit_interval:
                        await asyncio.sleep(min_edit_interval - elapsed)

                    if flusher_stop.is_set():
                        break

                    if accumulated_tokens:
                        partial = "".join(accumulated_tokens)
                        preview = partial[:1800] + " ▌"
                    elif status_hint:
                        preview = f"_{status_hint}_ ▌"
                    else:
                        continue

                    async with flusher_lock:
                        try:
                            if streamed_msg_id is None:
                                streamed_msg_id = await driver.send_message(
                                    recipient=msg.conversation_id,
                                    content=preview,
                                )
                                last_edit_ts = time.monotonic()
                            else:
                                await driver.edit_message(
                                    recipient=msg.conversation_id,
                                    message_id=streamed_msg_id,
                                    content=preview,
                                )
                                last_edit_ts = time.monotonic()
                        except Exception:
                            pass

            flusher_task = asyncio.create_task(_flusher_loop())

            async def _on_channel_event(ev: dict[str, Any]) -> None:
                nonlocal status_hint
                ev_type = ev.get("event")

                # Non-blocking event handler: updates buffer & signals flusher
                if ev_type == "reasoning":
                    if not status_hint and not accumulated_tokens:
                        status_hint = "🤔 Đang suy nghĩ câu trả lời..."
                        flusher_dirty.set()

                elif ev_type == "tool_call":
                    tool_name = str(ev.get("data", {}).get("name", "")).lower()
                    if any(w in tool_name for w in ("search", "research", "browse", "crawl")):
                        status_hint = "🔍 Đang tìm kiếm và tra cứu thông tin..."
                    elif any(w in tool_name for w in ("code", "python", "bash", "sandbox")):
                        status_hint = "💻 Đang chạy mã nguồn..."
                    elif "delegate" in tool_name or "agent" in tool_name:
                        status_hint = "🤖 Đang phối hợp chuyên gia AI..."
                    else:
                        status_hint = "⚙️ Đang xử lý yêu cầu..."
                    flusher_dirty.set()

                elif ev_type == "token":
                    txt = ev.get("data", {}).get("content", "")
                    if txt:
                        accumulated_tokens.append(txt)
                        flusher_dirty.set()

            try:
                # Call agent loop with session context and streaming event listener
                result = await run_agent_loop(
                    agent=agent,
                    message=msg.content,
                    db=db,
                    session_id=session.id,
                    user_id=connection.created_by_user_id,
                    user_role="user" if connection.created_by_user_id else None,
                    record_stream=False,
                    execution_policy=normalize_execution_policy(session.execution_policy),
                    on_event=_on_channel_event,
                )
            finally:
                stop_typing.set()
                typing_task.cancel()
                flusher_stop.set()
                flusher_dirty.set()
                flusher_task.cancel()
                try:
                    await asyncio.gather(typing_task, flusher_task, return_exceptions=True)
                except Exception:
                    pass

            if result.error:
                await logger.aerror(
                    "channel_message_agent_error",
                    agent_id=agent.id,
                    error=result.error,
                )
                reply_text = f"Xin lỗi, đã có lỗi xảy ra: {result.error}"
            else:
                reply_text = result.content

            # Finalize reply: edit streamed message or send new message
            from app.channels.driver import split_message

            chunks = split_message(
                reply_text,
                max_length=1900 if connection.provider == "discord" else 4000,
            )
            first_chunk = chunks[0] if chunks else reply_text

            external_id = streamed_msg_id
            if streamed_msg_id:
                edited = await driver.edit_message(
                    recipient=msg.conversation_id,
                    message_id=streamed_msg_id,
                    content=first_chunk,
                )
                if not edited:
                    external_id = await driver.send_message(
                        recipient=msg.conversation_id,
                        content=first_chunk,
                    )
                for next_chunk in chunks[1:]:
                    await driver.send_message(
                        recipient=msg.conversation_id,
                        content=next_chunk,
                    )
            else:
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
