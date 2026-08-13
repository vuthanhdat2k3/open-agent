from __future__ import annotations

import asyncio
import base64
import hmac
import json
from typing import Any

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.customer_intelligence import GmailNotification
from app.repositories.customer_intelligence import EmailConnectionRepository
from app.repositories.outbox import OutboxRepository

_jwks_client: jwt.PyJWKClient | None = None


def _decode_data(value: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "invalid Pub/Sub message data") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid Gmail notification payload")
    return payload


def _verify_oidc_token(token: str, audience: str) -> dict[str, Any]:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            "https://www.googleapis.com/oauth2/v3/certs", cache_jwk_set=True, lifespan=300
        )
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
    )


async def verify_push_authorization(request: Request) -> None:
    settings = get_settings()
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    if settings.gmail_pubsub_audience:
        if not token:
            raise HTTPException(401, "missing Pub/Sub OIDC token")
        try:
            claims = await asyncio.to_thread(_verify_oidc_token, token, settings.gmail_pubsub_audience)
        except (jwt.PyJWTError, OSError, ValueError) as exc:
            raise HTTPException(401, "invalid Pub/Sub OIDC token") from exc
        if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
            raise HTTPException(401, "invalid Pub/Sub token issuer")
        if settings.gmail_pubsub_service_account and claims.get("email") != settings.gmail_pubsub_service_account:
            raise HTTPException(403, "unexpected Pub/Sub service account")
        return
    if settings.gmail_pubsub_shared_token and not hmac.compare_digest(token, settings.gmail_pubsub_shared_token):
        raise HTTPException(401, "invalid webhook token")
    if settings.runtime == "production":
        raise HTTPException(503, "Pub/Sub OIDC is not configured")


async def ingest_push(db: AsyncSession, request: Request, body: dict[str, Any]) -> dict[str, str]:
    await verify_push_authorization(request)
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict) or not isinstance(message.get("data"), str):
        raise HTTPException(400, "invalid Pub/Sub envelope")
    gmail = _decode_data(message["data"])
    email_address = str(gmail.get("emailAddress", "")).lower().strip()
    history_id = str(gmail.get("historyId", "")).strip()
    if not email_address or not history_id or len(history_id) > 64:
        raise HTTPException(400, "invalid Gmail notification")
    connection = await EmailConnectionRepository(db).get_gmail_by_account(email_address)
    if connection is None:
        # Ack unknown mailboxes: Google will retry forever otherwise, while no
        # tenant can be safely inferred from the push body.
        return {"status": "ignored"}
    connection_id = connection.id
    org_id = connection.org_id
    user_id = connection.created_by_user_id
    notification = GmailNotification(
        org_id=org_id,
        connection_id=connection_id,
        history_id=history_id,
        provider_notification_id=str(message.get("messageId", ""))[:256] or None,
    )
    try:
        db.add(notification)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(GmailNotification).where(
                GmailNotification.connection_id == connection_id,
                GmailNotification.history_id == history_id,
            )
        )
        if existing is not None:
            return {"status": "duplicate"}
        raise
    await OutboxRepository(db).add_event(
        event_type="gmail.history_sync.requested",
        aggregate_type="gmail_connection",
        aggregate_id=connection_id,
        org_id=org_id,
        user_id=user_id,
        correlation_id=notification.id,
        payload={"connection_id": connection.id, "history_id": history_id},
        dedupe_key=f"gmail-history:{connection_id}:{history_id}",
    )
    await db.commit()
    return {"status": "accepted"}
