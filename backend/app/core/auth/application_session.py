from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.application_session import ApplicationSession
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_application_session(
    db: AsyncSession,
    *,
    user: User,
    membership: Membership,
    request: Request,
    response: Response,
    zitadel_session_id: str | None = None,
) -> ApplicationSession:
    settings = get_settings()
    raw_session = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    now = _now()
    session = ApplicationSession(
        session_token_hash=_hash(raw_session),
        csrf_token_hash=_hash(raw_csrf),
        user_id=user.id,
        organization_id=membership.org_id,
        membership_id=membership.id,
        zitadel_session_id=zitadel_session_id,
        auth_time=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=settings.application_session_idle_minutes),
        absolute_expires_at=now + timedelta(hours=settings.application_session_absolute_hours),
        created_ip_hash=_hash(request.client.host) if request.client else None,
        created_user_agent_hash=_hash(request.headers.get("user-agent", "")),
    )
    db.add(session)
    await db.flush()
    response.set_cookie(
        settings.application_session_cookie_name,
        raw_session,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.application_session_absolute_hours * 3600,
        path="/",
    )
    response.set_cookie(
        settings.application_session_csrf_cookie_name,
        raw_csrf,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.application_session_absolute_hours * 3600,
        path="/",
    )
    return session


async def resolve_application_session(
    db: AsyncSession, *, raw_token: str, request: Request
) -> tuple[User, Membership, ApplicationSession]:
    result = await db.execute(
        select(ApplicationSession, User, Membership, Organization)
        .join(User, User.id == ApplicationSession.user_id)
        .join(Membership, Membership.id == ApplicationSession.membership_id)
        .join(Organization, Organization.id == ApplicationSession.organization_id)
        .where(ApplicationSession.session_token_hash == _hash(raw_token))
    )
    row = result.first()
    now = _now()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid application session")
    session, user, membership, organization = row
    if (
        session.revoked_at is not None
        or session.idle_expires_at < now
        or session.absolute_expires_at < now
        or not user.is_active
        or user.lifecycle_status != "active"
        or membership.lifecycle_status != "active"
        or organization.lifecycle_status != "active"
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Application session expired or revoked")
    if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        settings = get_settings()
        csrf = request.headers.get("X-CSRF-Token")
        if not csrf or _hash(csrf) != session.csrf_token_hash:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
    session.last_seen_at = now
    session.idle_expires_at = now + timedelta(minutes=get_settings().application_session_idle_minutes)
    return user, membership, session


def clear_application_session(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.application_session_cookie_name, path="/")
    response.delete_cookie(settings.application_session_csrf_cookie_name, path="/")
