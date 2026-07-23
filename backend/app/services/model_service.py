from __future__ import annotations

from app.models.model import Model
from app.repositories.model_repo import ModelRepository
from app.repositories.provider_repo import ProviderRepository


class ModelService:
    def __init__(self, db):
        self.repo = ModelRepository(db)
        self.provider_repo = ProviderRepository(db)

    async def create(self, org_id: str, data: dict, user_id: str | None = None) -> Model:
        prov = await self.provider_repo.get(org_id, data["provider_id"])
        if prov is None:
            raise ValueError("provider not found")
        data["org_id"] = org_id
        if user_id:
            data["created_by_user_id"] = user_id
        return await self.repo.create(Model(**data))

    async def update(self, org_id: str, id: str, data: dict) -> Model:
        m = await self.repo.get(org_id, id)
        if m is None:
            raise ValueError("model not found")
        return await self.repo.update(m, data)

    async def delete(self, org_id: str, id: str) -> bool:
        return await self.repo.delete(org_id, id)

    async def list(self, org_id: str) -> list[Model]:
        return await self.repo.list(org_id)

    async def get(self, org_id: str, id: str) -> Model | None:
        return await self.repo.get(org_id, id)
