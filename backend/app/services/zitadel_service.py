from __future__ import annotations

import logging
import os
from typing import Any
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class ZitadelProvisioningService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_pat(self) -> str | None:
        if self.settings.zitadel_admin_pat:
            return self.settings.zitadel_admin_pat
        if self.settings.zitadel_pat_path and os.path.exists(self.settings.zitadel_pat_path):
            try:
                with open(self.settings.zitadel_pat_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning("Failed to read Zitadel PAT from %s: %s", self.settings.zitadel_pat_path, e)
        return None

    def get_api_base_url(self) -> str:
        return (self.settings.zitadel_internal_url or self.settings.zitadel_issuer_url or "http://127.0.0.1.sslip.io").rstrip("/")

    async def provision_user(
        self,
        email: str,
        display_name: str | None = None,
        initial_password: str = "OpenAgent@2026",
    ) -> dict[str, Any] | None:
        """Automatically creates a human user on ZITADEL if not already existing."""
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
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{base_url}/v2/users/human", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    logger.info("Successfully auto-provisioned user %s on ZITADEL (id: %s)", email_clean, data.get("userId"))
                    return data
                elif res.status_code in {400, 409}:
                    logger.info("ZITADEL user %s already exists or returned %s: %s", email_clean, res.status_code, res.text)
                    return None
                else:
                    logger.warning("Failed to auto-provision user on ZITADEL (status %s): %s", res.status_code, res.text)
                    return None
        except Exception as exc:
            logger.warning("Error communicating with ZITADEL API to provision %s: %s", email_clean, exc)
            return None
