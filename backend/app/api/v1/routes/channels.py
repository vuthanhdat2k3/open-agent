from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.factory import build_channel_driver
from app.core.authz.policy import PrincipalContext
from app.core.workflow.queue import _redis_settings
from app.dependencies import (
    get_current_org_id,
    get_current_user,
    get_db,
    require_permission,
)
from app.models.channel import ChannelConversation
from app.models.user import User
from app.schemas.channel import (
    ChannelConnectionCreate,
    ChannelConnectionOut,
    ChannelConnectionUpdate,
    ChannelMessageOut,
    ChannelTestResponse,
)
from app.services.channel_service import ChannelService

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _can_manage_all(authz: PrincipalContext) -> bool:
    """Operators/admins manage org-wide connections; users only their own."""
    return authz.allows("channels:manage")


def _can_personal_manage(authz: PrincipalContext) -> bool:
    """Personal management of one's own connections."""
    return authz.allows("channels:personal:manage")


def _connection_to_out(conn, latest_session_id: str | None = None, user: User | None = None) -> dict[str, Any]:
    """Convert a ChannelConnection to API response dict (without sensitive data)."""
    return {
        "id": conn.id,
        "org_id": conn.org_id,
        "provider": conn.provider,
        "bot_username": conn.bot_username,
        "status": conn.status,
        "config": conn.config,
        "created_by_user_id": conn.created_by_user_id,
        "creator_email": user.email if user else None,
        "creator_name": user.display_name if user else None,
        "latest_session_id": latest_session_id,
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }


async def _get_latest_session_ids(
    db: AsyncSession, org_id: str, connection_ids: list[str]
) -> dict[str, str]:
    if not connection_ids:
        return {}

    stmt = (
        select(ChannelConversation.connection_id, ChannelConversation.session_id)
        .where(
            ChannelConversation.org_id == org_id,
            ChannelConversation.connection_id.in_(connection_ids),
        )
        .order_by(ChannelConversation.updated_at.desc())
    )
    res = await db.execute(stmt)
    result: dict[str, str] = {}
    for conn_id, sess_id in res.all():
        if conn_id not in result:
            result[conn_id] = sess_id
    return result


@router.get(
    "",
    response_model=list[ChannelConnectionOut],
    dependencies=[Depends(require_permission("channels:read"))],
)
async def list_connections(
    provider: str | None = None,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """List channel connections visible to the current user.

    - Operators/admins (channels:manage) see shared org-wide connections
      plus any personal ones.
    - Users only see their own personal connections (owner == user_id).
    """
    service = ChannelService(db)
    can_manage_all = _can_manage_all(authz)
    connections = await service.list_connections(
        org_id,
        provider,
        owner_user_id=None if can_manage_all else authz.user_id,
        include_all=can_manage_all,
    )
    session_map = await _get_latest_session_ids(
        db, org_id, [c.id for c in connections]
    )

    # Join User to get creator email/name (avoid N+1)
    creator_ids = [c.created_by_user_id for c in connections if c.created_by_user_id]
    user_map: dict[str, User] = {}
    if creator_ids:
        res = await db.execute(select(User).where(User.id.in_(creator_ids)))
        for u in res.scalars().all():
            user_map[u.id] = u

    return [
        _connection_to_out(
            c,
            latest_session_id=session_map.get(c.id),
            user=user_map.get(c.created_by_user_id) if c.created_by_user_id else None,
        )
        for c in connections
    ]


@router.post(
    "",
    response_model=ChannelConnectionOut,
    status_code=201,
)
async def create_connection(
    body: ChannelConnectionCreate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
    current_user=Depends(get_current_user),
):
    """Create a new channel connection.

    - Operators/admins (channels:manage) create shared org-wide connections
      (owner = NULL).
    - Users (channels:personal:manage) create a personal connection tied to
      their own user_id.
    """
    if not (_can_manage_all(authz) or _can_personal_manage(authz)):
        raise HTTPException(
            403,
            "Permission denied: requires channels:manage or channels:personal:manage",
        )
    owner_user_id = None if _can_manage_all(authz) else current_user.id
    service = ChannelService(db)
    try:
        connection = await service.create_connection(
            org_id=org_id,
            provider=body.provider,
            bot_token=body.bot_token,
            config=body.config,
            bot_username=body.bot_username or "",
            owner_user_id=owner_user_id,
        )
        if connection.provider == "discord" and connection.status == "active":
            try:
                from app.channels.gateway import get_discord_manager
                await get_discord_manager().add_bot(connection)
            except Exception as e:
                import structlog
                await structlog.get_logger(__name__).awarning("discord_bot_auto_start_failed", error=str(e))
        elif connection.provider == "telegram" and connection.status == "active":
            try:
                from app.channels.gateway import get_telegram_manager
                await get_telegram_manager().add_bot(connection)
            except Exception as e:
                import structlog
                await structlog.get_logger(__name__).awarning("telegram_bot_auto_start_failed", error=str(e))
        return _connection_to_out(connection)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get(
    "/{connection_id}",
    response_model=ChannelConnectionOut,
    dependencies=[Depends(require_permission("channels:read"))],
)
async def get_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Get a channel connection by ID.

    Operators/admins can fetch any org connection; users can only fetch
    connections they own.
    """
    service = ChannelService(db)
    conn = await service.get_connection(org_id, connection_id)
    if conn is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and conn.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")
    session_map = await _get_latest_session_ids(db, org_id, [conn.id])
    return _connection_to_out(conn, latest_session_id=session_map.get(conn.id))


@router.patch(
    "/{connection_id}",
    response_model=ChannelConnectionOut,
)
async def update_connection(
    connection_id: str,
    body: ChannelConnectionUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Update a channel connection.

    Same ownership rules as `GET /{connection_id}`.
    """
    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    updates = body.model_dump(exclude_unset=True)
    conn = await service.update_connection(org_id, connection_id, **updates)
    if conn is None:
        raise HTTPException(404, "Channel connection not found")

    if conn.provider == "discord":
        try:
            from app.channels.gateway import get_discord_manager
            mgr = get_discord_manager()
            if conn.status == "active":
                await mgr.remove_bot(conn.id)
                await mgr.add_bot(conn)
            else:
                await mgr.remove_bot(conn.id)
        except Exception as e:
            import structlog
            await structlog.get_logger(__name__).awarning("discord_bot_update_gateway_failed", error=str(e))
    elif conn.provider == "telegram":
        try:
            from app.channels.gateway import get_telegram_manager
            tg_mgr = get_telegram_manager()
            if conn.status == "active":
                await tg_mgr.remove_bot(conn.id)
                await tg_mgr.add_bot(conn)
            else:
                await tg_mgr.remove_bot(conn.id)
        except Exception as e:
            import structlog
            await structlog.get_logger(__name__).awarning("telegram_bot_update_gateway_failed", error=str(e))

    return _connection_to_out(conn)


@router.delete(
    "/{connection_id}",
)
async def delete_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Delete a channel connection.

    Same ownership rules as `GET /{connection_id}`.
    """
    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    if existing.provider == "discord":
        try:
            from app.channels.gateway import get_discord_manager
            await get_discord_manager().remove_bot(connection_id)
        except Exception:
            pass
    elif existing.provider == "telegram":
        try:
            from app.channels.gateway import get_telegram_manager
            await get_telegram_manager().remove_bot(connection_id)
        except Exception:
            pass

    if not await service.delete_connection(org_id, connection_id):
        raise HTTPException(404, "Channel connection not found")
    return {"ok": True}


@router.post("/{connection_id}/setup-webhook")
async def setup_webhook(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Set up webhook URL for a Telegram bot.

    Requires OPENAGENT_PUBLIC_URL to be set in .env (e.g., https://your-domain.com).
    """
    from app.config import get_settings

    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    if existing.provider != "telegram":
        raise HTTPException(400, "Webhook setup only applies to Telegram connections")

    settings = get_settings()
    public_url = getattr(settings, "public_url", None)
    if not public_url:
        raise HTTPException(
            400,
            "OPENAGENT_PUBLIC_URL not configured. Set it in .env to your public domain.",
        )

    driver = build_channel_driver(existing)
    webhook_url = f"{public_url.rstrip('/')}/webhooks/telegram"
    await driver.setup_webhook(webhook_url, secret_token=existing.webhook_secret)
    return {"ok": True, "webhook_url": webhook_url}


@router.post(
    "/{connection_id}/test",
    response_model=ChannelTestResponse,
)
async def test_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Test a channel connection."""
    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    result = await service.test_connection(org_id, connection_id)
    return ChannelTestResponse(**result)


@router.post("/{connection_id}/start")
async def start_bot(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Start the Discord bot gateway for this connection."""
    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    if existing.provider != "discord":
        raise HTTPException(400, "Gateway start only applies to Discord connections")

    from app.channels.gateway import get_discord_manager
    await get_discord_manager().add_bot(existing)
    return {"ok": True, "message": "Discord bot starting"}


@router.post("/{connection_id}/stop")
async def stop_bot(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """Stop the Discord bot gateway for this connection."""
    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    from app.channels.gateway import get_discord_manager
    await get_discord_manager().remove_bot(connection_id)
    return {"ok": True, "message": "Discord bot stopped"}


@router.get(
    "/{connection_id}/messages",
    response_model=list[ChannelMessageOut],
    dependencies=[Depends(require_permission("channels:read"))],
)
async def list_messages(
    connection_id: str,
    limit: int = 50,
    offset: int = 0,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    authz: PrincipalContext = Depends(require_permission("channels:read")),
):
    """List messages for a channel connection."""
    service = ChannelService(db)
    existing = await service.get_connection(org_id, connection_id)
    if existing is None:
        raise HTTPException(404, "Channel connection not found")
    if not _can_manage_all(authz) and existing.created_by_user_id != authz.user_id:
        raise HTTPException(403, "Not your personal channel connection")

    messages = await service.list_messages(org_id, connection_id, limit, offset)
    return [
        ChannelMessageOut(
            id=m.id,
            org_id=m.org_id,
            connection_id=m.connection_id,
            direction=m.direction,
            external_message_id=m.external_message_id,
            sender_id=m.sender_id,
            sender_name=m.sender_name,
            conversation_id=m.conversation_id,
            message_type=m.message_type,
            content=m.content,
            metadata=m.metadata_json,
            agent_id=m.agent_id,
            created_at=m.created_at,
        )
        for m in messages
    ]


# Webhook routers (unauthenticated - verified by secret)
webhook_router = APIRouter(prefix="/webhooks", tags=["channel-webhooks"])


@webhook_router.post("/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Telegram webhook updates."""
    payload = await request.json()

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    service = ChannelService(db)
    connection = await service.find_connection_by_webhook_secret("telegram", secret)
    if connection is None:
        raise HTTPException(401, "Invalid webhook secret")

    driver = build_channel_driver(connection)
    inbound = await driver.parse_webhook(payload)

    if inbound:
        msg = await service.handle_inbound_message(
            connection.org_id, connection.id, inbound
        )
        await db.commit()

        from arq import create_pool


        pool = await create_pool(_redis_settings())
        try:
            await pool.enqueue_job(
                "process_channel_message",
                str(connection.org_id),
                str(connection.id),
                str(msg.id),
            )
        finally:
            await pool.close()

    return {"ok": True}


@webhook_router.post("/discord")
async def discord_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Discord interaction webhooks with Ed25519 signature verification."""
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    payload = await request.body()
    body_str = payload.decode("utf-8")

    import json
    data = json.loads(body_str)

    if data.get("type") == 1:
        return {"type": 1}  # PONG

    guild_id = data.get("guild_id")
    service = ChannelService(db)

    if not guild_id:
        raise HTTPException(400, "Missing guild_id")

    connections = await service.list_connections_by_guild(guild_id)
    if not connections:
        raise HTTPException(404, "No channel connection for this guild")

    connection = connections[0]
    public_key = connection.config.get("public_key", "")

    if public_key:
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
            message = timestamp.encode("utf-8") + payload
            pubkey.verify(bytes.fromhex(signature), message)
        except (InvalidSignature, ValueError) as e:
            raise HTTPException(401, f"Invalid signature: {e}")
        except Exception as e:
            raise HTTPException(500, f"Signature verification error: {e}")

    driver = build_channel_driver(connection)
    inbound = await driver.parse_webhook(data)

    if inbound:
        msg = await service.handle_inbound_message(
            connection.org_id, connection.id, inbound
        )
        await db.commit()

        from arq import create_pool


        pool = await create_pool(_redis_settings())
        try:
            await pool.enqueue_job(
                "process_channel_message",
                str(connection.org_id),
                str(connection.id),
                str(msg.id),
            )
        finally:
            await pool.close()

    return {"type": 5}  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
