from fastapi import HTTPException, Request, status

from app.config import get_settings

settings = get_settings()


async def verify_api_key(request: Request) -> None:
    """Guard routes. In localhost-only mode (no api_key set) everything is allowed."""
    if not settings.api_key:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth[len("Bearer ") :].strip()
    if token != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def allowed_origins() -> list[str]:
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
