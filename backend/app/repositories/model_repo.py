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
    async def list_all(self, org_id: str, query: str | None = None) -> list[Model]:
        stmt = select(Model).where(Model.org_id == org_id).order_by(Model.created_at.desc())
        if query:
            pattern = f"%{query.strip()}%"
            from sqlalchemy import or_

            stmt = stmt.where(or_(Model.name.ilike(pattern), Model.display_name.ilike(pattern)))
        res = await self.db.execute(stmt)
        return list(res.scalars().all())



    async def list_active(self, org_id: str) -> list[Model]:
        res = await self.db.execute(
            select(Model).where(Model.org_id == org_id, Model.active.is_(True))
        )
        return list(res.scalars().all())
