from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.config import get_settings

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ZitadelProvisioningService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_pat(self) -> str | None:
        if self.settings.zitadel_admin_pat:
            return self.settings.zitadel_admin_pat
        if self.settings.zitadel_pat_path and os.path.exists(self.settings.zitadel_pat_path):
            try:
                with open(self.settings.zitadel_pat_path, encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning("Failed to read Zitadel PAT from %s: %s", self.settings.zitadel_pat_path, e)
        return None

    def get_api_base_url(self) -> str:
        return (self.settings.zitadel_internal_url or self.settings.zitadel_issuer_url or "http://127.0.0.1.sslip.io").rstrip("/")

    def get_host_header(self) -> str:
        issuer = self.settings.zitadel_issuer_url or "http://127.0.0.1.sslip.io"
        return issuer.removeprefix("http://").removeprefix("https://").split("/", 1)[0].split(":", 1)[0]

    async def get_user_id_by_email(self, email: str) -> str | None:
        pat = self.get_pat()
        if not pat:
            return None
        base_url = self.get_api_base_url()
        headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json",
            "Host": self.get_host_header(),
        }
        target_email = email.strip().lower()
        search_payload = {
            "query": {
                "limit": 100,
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/v2/users", json=search_payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    results = data.get("result") or []
                    for r in results:
                        user_email = (r.get("human", {}).get("email", {}).get("email") or "").lower()
                        user_name = (r.get("username") or "").lower()
                        if target_email in (user_email, user_name):
                            return r.get("userId")
        except Exception as exc:
            logger.warning("Error looking up Zitadel user by email %s: %s", email, exc)
        return None

    async def set_user_password(self, user_id: str, new_password: str) -> bool:
        pat = self.get_pat()
        if not pat:
            return False
        base_url = self.get_api_base_url()
        headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json",
            "Host": self.get_host_header(),
        }
        payload = {
            "newPassword": {
                "password": new_password,
                "changeRequired": False,
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/v2/users/{user_id}/password", json=payload, headers=headers)
                if res.status_code == 200:
                    logger.info("Successfully updated Zitadel password for userId %s", user_id)
                    return True
                else:
                    logger.warning("Failed to update Zitadel password for %s (status %s): %s", user_id, res.status_code, res.text)
                    return False
        except Exception as exc:
            logger.warning("Error updating Zitadel password for %s: %s", user_id, exc)
            return False

    async def verify_user_password(self, login_name: str, password: str) -> bool:
        """Verifies a user's credentials against ZITADEL session API."""
        pat = self.get_pat()
        if not pat:
            return False
        base_url = self.get_api_base_url()
        headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json",
            "Host": self.get_host_header(),
        }
        payload = {
            "checks": {
                "user": {"loginName": login_name.strip().lower()},
                "password": {"password": password},
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/v2/sessions", json=payload, headers=headers)
                return res.status_code == 201
        except Exception as exc:
            logger.warning("Error verifying Zitadel credentials for %s: %s", login_name, exc)
            return False

    async def provision_user(
        self,
        email: str,
        display_name: str | None = None,
        initial_password: str = "OpenAgent@2026",
    ) -> dict[str, Any] | None:
        """Automatically creates a human user on ZITADEL if not already existing, or syncs password if existing."""
        if self.settings.auth_provider != "zitadel":
            return None

        pat = self.get_pat()
        if not pat:
            logger.info("Zitadel PAT not configured; skipping automatic Zitadel user provisioning for %s", email)
            return None

        base_url = self.get_api_base_url()
        email_clean = email.strip().lower()
        parts = (display_name or email_clean.split("@", 1)[0]).split(" ", 1)
        given_name = parts[0]
        family_name = parts[1] if len(parts) > 1 else "User"

        payload = {
            "profile": {
                "givenName": given_name,
                "familyName": family_name,
                "displayName": display_name or email_clean.split("@", 1)[0],
            },
            "email": {
                "email": email_clean,
                "isVerified": True,
            },
            "password": {
                "password": initial_password or "OpenAgent@2026",
                "changeRequired": False,
            },
        }

        headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json",
            "Host": self.get_host_header(),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/v2/users/human", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    logger.info("Successfully auto-provisioned user %s on ZITADEL (id: %s)", email_clean, data.get("userId"))
                    return data
                elif res.status_code == 409 or (res.status_code == 400 and "already exists" in res.text.lower()):
                    logger.info("ZITADEL user %s already exists; syncing password if provided", email_clean)
                    user_id = await self.get_user_id_by_email(email_clean)
                    if user_id and initial_password:
                        await self.set_user_password(user_id, initial_password)
                    return {"userId": user_id}
                elif res.status_code == 400:
                    error_data = {}
                    try:
                        error_data = res.json()
                    except Exception:
                        pass
                    msg = error_data.get("message") or res.text
                    logger.warning("ZITADEL user provisioning rejected for %s: %s", email_clean, msg)
                    raise HTTPException(status_code=400, detail=f"ZITADEL: {msg}")
                else:
                    logger.warning("Failed to auto-provision user on ZITADEL (status %s): %s", res.status_code, res.text)
                    return None
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Error communicating with ZITADEL API to provision %s: %s", email_clean, exc)
            return None
