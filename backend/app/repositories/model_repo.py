from app.models.model import Model
from app.repositories.base import BaseRepository


class ModelRepository(BaseRepository[Model]):
    def __init__(self, db):
        super().__init__(Model, db)

    async def list_by_provider(self, provider_id: str) -> list[Model]:
        from sqlalchemy import select

        res = await self.db.execute(
            select(Model).where(Model.provider_id == provider_id)
        )
        return list(res.scalars().all())

    async def list_active(self) -> list[Model]:
        from sqlalchemy import select

        res = await self.db.execute(select(Model).where(Model.active.is_(True)))
        return list(res.scalars().all())
