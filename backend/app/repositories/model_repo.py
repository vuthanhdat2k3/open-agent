from sqlalchemy import select

from app.models.model import Model
from app.repositories.base import BaseRepository


class ModelRepository(BaseRepository[Model]):
    def __init__(self, db):
        super().__init__(Model, db)

    async def list_by_provider(self, org_id: str, provider_id: str) -> list[Model]:
        res = await self.db.execute(
            select(Model).where(Model.org_id == org_id, Model.provider_id == provider_id)
        )
        return list(res.scalars().all())

    async def list_active(self, org_id: str) -> list[Model]:
        res = await self.db.execute(
            select(Model).where(Model.org_id == org_id, Model.active.is_(True))
        )
        return list(res.scalars().all())
