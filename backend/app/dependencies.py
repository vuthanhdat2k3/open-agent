from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.api_key import hash_api_key
from app.core.auth.jwt import verify_access_token
from app.core.authz.policy import has_permission
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.membership import Membership
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
    # Accept X-API-Key header or Authorization: Bearer <api_key>
    api_key_match = x_api_key == settings.api_key
    if not api_key_match:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key_match = auth_header.removeprefix("Bearer ") == settings.api_key
    if settings.api_key and api_key_match:
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
    db: AsyncSession = Depends(get_db),
) -> str:
    """Return org_id for current request context.

    If request is authenticated (request.state.user_id / org_id is set):
    - Uses authenticated org_id by default.
    - If X-Org-Id header is provided, verifies user membership in target org.
    - Raises 403 Forbidden if user attempts tenant override to an un-joined org.
    """
    header_org = request.headers.get("X-Org-Id")
    state_org = getattr(request.state, "org_id", None)
    user_id = getattr(request.state, "user_id", None)

    if user_id and header_org:
        if header_org != state_org:
            res = await db.execute(
                select(Membership).where(
                    Membership.org_id == header_org,
                    Membership.user_id == user_id,
                )
            )
            membership = res.scalar_one_or_none()
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User does not belong to organization '{header_org}'",
                )
        return header_org

    if state_org:
        return state_org

    if header_org:
        return header_org

    return DEFAULT_ORG_ID


def require_permission(permission: str):
    """Enforce RBAC permission check against the resolved request org_id.

    Note: Checks role in the org resolved by `get_current_org_id` (JWT home org or X-Org-Id).
    Nested routes with explicit path parameters (e.g. `/orgs/{id}/members`) must perform
    explicit resource-level membership checks to ensure operating on the target path org.
    """

    async def _checker(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        org_id: str = Depends(get_current_org_id),
    ) -> None:
        res = await db.execute(
            select(Membership).where(
                Membership.org_id == org_id,
                Membership.user_id == current_user.id,
            )
        )
        membership = res.scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this organization",
            )
        if not has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )

    return _checker


__all__ = [
    "get_db",
    "get_settings",
    "get_current_user",
    "get_current_org_id",
    "require_permission",
    "DEFAULT_ORG_ID",
]
