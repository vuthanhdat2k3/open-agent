from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.dependencies import DEFAULT_ORG_ID, get_current_user

settings = get_settings()
security_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bearer: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """Guard routes. Authenticates via JWT Bearer, Cookie, Database ApiKey, or machine OPENAGENT_API_KEY.

    Populates request.state.user_id and request.state.org_id for multi-tenancy.
    """
    try:
        await get_current_user(request=request, db=db, bearer=bearer, x_api_key=x_api_key)
        return
    except HTTPException:
        # Dev mode fallback: if no OPENAGENT_API_KEY configured and request has no auth credentials
        auth_header = request.headers.get("Authorization")
        has_auth = (
            bearer is not None
            or "access_token" in request.cookies
            or x_api_key is not None
            or bool(auth_header)
        )
        if not settings.api_key and not has_auth:
            request.state.org_id = request.headers.get("X-Org-Id", DEFAULT_ORG_ID)
            return
        raise


def allowed_origins() -> list[str]:
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
