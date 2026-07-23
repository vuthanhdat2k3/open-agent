from fastapi import Request

from app.config import get_settings
from app.db.session import get_db

DEFAULT_ORG_ID = "default-org-id"


async def get_current_org_id(request: Request) -> str:
    """Return org_id for current request context.

    Reads from X-Org-Id header or request.state if authenticated,
    falling back to DEFAULT_ORG_ID.
    """
    header_org = request.headers.get("X-Org-Id")
    if header_org:
        return header_org
    return getattr(request.state, "org_id", DEFAULT_ORG_ID)


__all__ = ["get_db", "get_settings", "get_current_org_id", "DEFAULT_ORG_ID"]
