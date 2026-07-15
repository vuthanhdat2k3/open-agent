from __future__ import annotations

import time

import httpx

from app.models.provider import Provider
from app.repositories.provider_repo import ProviderRepository
from app.core.llm import resolve_api_key


class ProviderService:
    def __init__(self, db):
        self.repo = ProviderRepository(db)
        self.db = db

    async def create(self, data: dict) -> Provider:
        if data.get("is_default"):
            existing = await self.repo.get_default()
            if existing:
                existing.is_default = False
                self.db.add(existing)
        prov = Provider(**data)
        return await self.repo.create(prov)

    async def update(self, id: str, data: dict) -> Provider:
        prov = await self.repo.get(id)
        if prov is None:
            raise ValueError("provider not found")
        if data.get("is_default"):
            existing = await self.repo.get_default()
            if existing and existing.id != id:
                existing.is_default = False
                self.db.add(existing)
        return await self.repo.update(prov, data)

    async def delete(self, id: str) -> bool:
        return await self.repo.delete(id)

    async def list(self) -> list[Provider]:
        return await self.repo.list_all()

    async def get(self, id: str) -> Provider | None:
        return await self.repo.get(id)

    async def test_connection(self, id: str) -> dict:
        prov = await self.repo.get(id)
        if prov is None:
            return {"ok": False, "message": "provider not found", "latency_ms": 0, "model_count": 0}
        try:
            api_key = resolve_api_key(prov)
        except RuntimeError as e:
            return {
                "ok": False,
                "message": str(e),
                "latency_ms": 0,
                "model_count": 0,
            }
        url = prov.base_url.rstrip("/") + "/models"
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {api_key}"}
                )
            elapsed = int((time.monotonic() - start) * 1000)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "message": f"HTTP {resp.status_code}",
                    "latency_ms": elapsed,
                    "model_count": 0,
                }
            data = resp.json()
            count = len(data.get("data", []))
            return {
                "ok": True,
                "message": "connected",
                "latency_ms": elapsed,
                "model_count": count,
            }
        except Exception as e:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            return {
                "ok": False,
                "message": f"error: {e}",
                "latency_ms": elapsed,
                "model_count": 0,
            }
