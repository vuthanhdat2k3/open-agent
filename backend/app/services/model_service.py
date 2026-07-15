from __future__ import annotations

from app.models.model import Model
from app.repositories.model_repo import ModelRepository
from app.repositories.provider_repo import ProviderRepository


class ModelService:
    def __init__(self, db):
        self.repo = ModelRepository(db)
        self.provider_repo = ProviderRepository(db)

    async def create(self, data: dict) -> Model:
        # validate provider exists
        prov = await self.provider_repo.get(data["provider_id"])
        if prov is None:
            raise ValueError("provider not found")
        return await self.repo.create(Model(**data))

    async def update(self, id: str, data: dict) -> Model:
        m = await self.repo.get(id)
        if m is None:
            raise ValueError("model not found")
        return await self.repo.update(m, data)

    async def delete(self, id: str) -> bool:
        return await self.repo.delete(id)

    async def list(self) -> list[Model]:
        return await self.repo.list()

    async def get(self, id: str) -> Model | None:
        return await self.repo.get(id)
