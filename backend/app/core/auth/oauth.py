from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from app.config import get_settings

settings = get_settings()

oauth = OAuth()

if settings.oauth_google_client_id and settings.oauth_google_client_secret:
    oauth.register(
        name="google",
        client_id=settings.oauth_google_client_id,
        client_secret=settings.oauth_google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if settings.oauth_github_client_id and settings.oauth_github_client_secret:
    oauth.register(
        name="github",
        client_id=settings.oauth_github_client_id,
        client_secret=settings.oauth_github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )
