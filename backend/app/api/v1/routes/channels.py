from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.factory import build_channel_driver
from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.channel import (
    ChannelConnectionCreate,
    ChannelConnectionOut,
    ChannelConnectionUpdate,
    ChannelMessageOut,
    ChannelTestResponse,
)
from app.services.channel_service import ChannelService

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _connection_to_out(conn) -> dict[str, Any]:
    """Convert a ChannelConnection to API response dict (without sensitive data)."""
    return {
        "id": conn.id,
        "org_id": conn.org_id,
        "provider": conn.provider,
        "bot_username": conn.bot_username,
        "status": conn.status,
        "config": conn.config,
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }


@router.get(
    "",
    response_model=list[ChannelConnectionOut],
    dependencies=[Depends(require_permission("channels:read"))],
)
async def list_connections(
    provider: str | None = None,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """List all channel connections for the org."""
    service = ChannelService(db)
    connections = await service.list_connections(org_id, provider)
    return [_connection_to_out(c) for c in connections]


@router.post(
    "",
    response_model=ChannelConnectionOut,
    status_code=201,
    dependencies=[Depends(require_permission("channels:manage"))],
)
async def create_connection(
    body: ChannelConnectionCreate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new channel connection."""
    service = ChannelService(db)
    try:
        connection = await service.create_connection(
            org_id=org_id,
            provider=body.provider,
            bot_token=body.bot_token,
            config=body.config,
            bot_username=body.bot_username or "",
        )
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
):
    """Get a channel connection by ID."""
    service = ChannelService(db)
    conn = await service.get_connection(org_id, connection_id)
    if conn is None:
        raise HTTPException(404, "Channel connection not found")
    return _connection_to_out(conn)


@router.patch(
    "/{connection_id}",
    response_model=ChannelConnectionOut,
    dependencies=[Depends(require_permission("channels:manage"))],
)
async def update_connection(
    connection_id: str,
    body: ChannelConnectionUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a channel connection."""
    service = ChannelService(db)
    updates = body.model_dump(exclude_unset=True)
    conn = await service.update_connection(org_id, connection_id, **updates)
    if conn is None:
        raise HTTPException(404, "Channel connection not found")
    return _connection_to_out(conn)


@router.delete(
    "/{connection_id}",
    dependencies=[Depends(require_permission("channels:manage"))],
)
async def delete_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a channel connection."""
    service = ChannelService(db)
    if not await service.delete_connection(org_id, connection_id):
        raise HTTPException(404, "Channel connection not found")
    return {"ok": True}


@router.post(
    "/{connection_id}/test",
    response_model=ChannelTestResponse,
    dependencies=[Depends(require_permission("channels:manage"))],
)
async def test_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Test a channel connection."""
    service = ChannelService(db)
    result = await service.test_connection(org_id, connection_id)
    return ChannelTestResponse(**result)


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
):
    """List messages for a channel connection."""
    service = ChannelService(db)
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

    # Get secret token from header
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    service = ChannelService(db)
    connection = await service.find_connection_by_webhook_secret("telegram", secret)
    if connection is None:
        raise HTTPException(401, "Invalid webhook secret")

    # Parse the update
    driver = build_channel_driver(connection)
    inbound = await driver.parse_webhook(payload)

    if inbound:
        # Store inbound message
        msg = await service.handle_inbound_message(
            connection.org_id, connection.id, inbound
        )
        await db.commit()

        # Trigger agent processing via ARQ
        from arq import create_pool

        from app.core.channels.jobs import process_channel_message
        from app.core.workflow.queue import _redis_settings

        pool = await create_pool(_redis_settings())
        try:
            await pool.enqueue_job(
                process_channel_message,
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

    # Handle PING (type 1) - Discord verifying the endpoint
    if data.get("type") == 1:
        return {"type": 1}  # PONG

    # Find connection by guild ID to get public key for verification
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
        # Verify Ed25519 signature
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

    # Parse and process interaction
    driver = build_channel_driver(connection)
    inbound = await driver.parse_webhook(data)

    if inbound:
        msg = await service.handle_inbound_message(
            connection.org_id, connection.id, inbound
        )
        await db.commit()

        # Trigger agent processing via ARQ
        from arq import create_pool

        from app.core.channels.jobs import process_channel_message
        from app.core.workflow.queue import _redis_settings

        pool = await create_pool(_redis_settings())
        try:
            await pool.enqueue_job(
                process_channel_message,
                str(connection.org_id),
                str(connection.id),
                str(msg.id),
            )
        finally:
            await pool.close()

    return {"type": 5}  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
