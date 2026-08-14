from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.customer_intelligence.security import decrypt_credentials, encrypt_credentials


def _sign(value: str) -> str:
    return hmac.new(get_settings().jwt_secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def create_oauth_state(user_id: str, org_id: str, kind: str, provider: str) -> str:
    payload = {"user_id": user_id, "org_id": org_id, "kind": kind, "provider": provider, "exp": int(time.time()) + 600}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{_sign(body)}"


def verify_oauth_state(state: str) -> dict[str, str]:
    try:
        body, signature = state.split(".", 1)
        if not hmac.compare_digest(signature, _sign(body)):
            raise ValueError("invalid OAuth state")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("OAuth state expired")
        return payload
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid OAuth state") from exc


def authorization_url(provider: str, kind: str, state: str, redirect_uri: str) -> str:
    if provider == "google":
        endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        scopes = {
            "email": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.send",
            "calendar": "https://www.googleapis.com/auth/calendar.events",
            "drive": "https://www.googleapis.com/auth/drive",
        }[kind]
        params = {"client_id": _client_credentials("google")[0], "redirect_uri": redirect_uri, "response_type": "code", "scope": f"openid email {scopes}", "access_type": "offline", "prompt": "consent", "state": state}
    else:
        raise ValueError(f"unsupported OAuth provider: {provider}; only google is enabled")
    return f"{endpoint}?{httpx.QueryParams(params)}"


async def account_email(provider: str, access_token: str) -> str:
    if provider == "google":
        url = "https://openidconnect.googleapis.com/v1/userinfo"
    else:
        raise ValueError(f"unsupported OAuth provider: {provider}; only google is enabled")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        response.raise_for_status()
        data = response.json()
    return (data.get("emailAddress") or data.get("mail") or data.get("userPrincipalName") or data.get("email") or "").lower()


def _client_credentials(provider: str) -> tuple[str, str]:
    settings = get_settings()
    if provider != "google":
        raise ValueError(f"unsupported OAuth provider: {provider}; only google is enabled")
    return settings.ci_google_oauth_client_id, settings.ci_google_oauth_client_secret


async def exchange_code(provider: str, code: str, redirect_uri: str, kind: str = "email") -> dict[str, Any]:
    client_id, client_secret = _client_credentials(provider)
    if not client_id or not client_secret:
        raise ValueError(f"OAuth client is not configured for {provider}")
    url = "https://oauth2.googleapis.com/token"
    data = {"code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri, "grant_type": "authorization_code"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, data=data)
        response.raise_for_status()
        return response.json()


async def refresh_provider_token(provider: str, credentials: dict[str, Any]) -> dict[str, Any] | None:
    if provider not in {"gmail", "google"}:
        return None
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        return None
    client_id, client_secret = _client_credentials("google")
    if not client_id or not client_secret:
        return None
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"},
        )
        response.raise_for_status()
        payload = response.json()
    updated = dict(credentials)
    updated.update({key: payload[key] for key in ("access_token", "expires_in", "scope", "token_type") if key in payload})
    return updated


async def revoke_provider_token(provider: str, credentials: dict[str, Any]) -> None:
    token = credentials.get("access_token")
    if not token or provider not in {"gmail", "google"}:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post("https://oauth2.googleapis.com/revoke", params={"token": token})
        response.raise_for_status()


async def load_fresh_credentials(db: AsyncSession, connection: Any) -> dict[str, Any]:
    if not connection.credentials_enc:
        raise ValueError("connection has no credentials")
    credentials = decrypt_credentials(connection.credentials_enc)
    expires_at = float(credentials.get("expires_at", 0) or 0)
    if expires_at and expires_at > time.time() + 60:
        return credentials
    oauth_provider = credentials.get("oauth_provider")
    if not oauth_provider or not credentials.get("refresh_token"):
        return credentials
    refreshed = await refresh_provider_token(oauth_provider, credentials)
    if refreshed is None:
        return credentials
    refreshed["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
    connection.credentials_enc = encrypt_credentials(refreshed)
    await db.commit()
    await db.refresh(connection)
    return refreshed
