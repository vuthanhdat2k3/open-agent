from __future__ import annotations

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.dependencies import get_current_user

security_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bearer: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    """Authenticate through the central identity dependency only."""
    await get_current_user(request=request, db=db, bearer=bearer, x_api_key=x_api_key)


def allowed_origins() -> list[str]:
    return [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
