from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.api_key import hash_api_key
from app.core.auth.jwt import verify_access_token
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.user import User

DEFAULT_ORG_ID = "default-org-id"
security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bearer: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> User:
    # 1. Check Bearer token or access_token cookie
    token = None
    if bearer and bearer.credentials:
        token = bearer.credentials
    elif "access_token" in request.cookies:
        token = request.cookies["access_token"]

    if token:
        try:
            payload = verify_access_token(token)
            user_id = payload.get("sub")
            org_id = payload.get("org_id")
            if user_id:
                res = await db.execute(
                    select(User).where(User.id == user_id, User.is_active.is_(True))
                )
                user = res.scalar_one_or_none()
                if user:
                    request.state.user_id = user.id
                    request.state.org_id = org_id or DEFAULT_ORG_ID
                    return user
        except Exception:
            pass

    # 2. Check X-API-Key header
    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        res = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.revoked_at.is_(None),
            )
        )
        api_key_obj = res.scalar_one_or_none()
        if api_key_obj:
            now = datetime.now(timezone.utc)
            if api_key_obj.expires_at is not None:
                exp = api_key_obj.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API key expired",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

            request.state.org_id = api_key_obj.org_id
            request.state.user_id = api_key_obj.created_by_user_id
            if api_key_obj.created_by_user_id:
                res_u = await db.execute(
                    select(User).where(
                        User.id == api_key_obj.created_by_user_id, User.is_active.is_(True)
                    )
                )
                user = res_u.scalar_one_or_none()
                if user:
                    return user

    # 3. Global OPENAGENT_API_KEY machine fallback (only if settings.api_key is set and matches)
    settings = get_settings()
    if settings.api_key and x_api_key == settings.api_key:
        res_admin = await db.execute(select(User).limit(1))
        admin_user = res_admin.scalar_one_or_none()
        if admin_user:
            request.state.org_id = getattr(request.state, "org_id", DEFAULT_ORG_ID)
            request.state.user_id = admin_user.id
            return admin_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_org_id(
    request: Request,
) -> str:
    """Return org_id for current request context."""
    header_org = request.headers.get("X-Org-Id")
    if header_org:
        return header_org
    if hasattr(request.state, "org_id") and request.state.org_id:
        return request.state.org_id
    return DEFAULT_ORG_ID


__all__ = ["get_db", "get_settings", "get_current_user", "get_current_org_id", "DEFAULT_ORG_ID"]
