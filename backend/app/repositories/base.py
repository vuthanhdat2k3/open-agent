from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get(self, org_id: str, id: str) -> ModelType | None:
        if not org_id:
            raise TypeError("org_id is required")
        res = await self.db.execute(
            select(self.model).where(self.model.id == id, self.model.org_id == org_id)
        )
        return res.scalar_one_or_none()

    async def list(self, org_id: str, limit: int = 100, offset: int = 0) -> list[ModelType]:
        if not org_id:
            raise TypeError("org_id is required")
        res = await self.db.execute(
            select(self.model)
            .where(self.model.org_id == org_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def create(self, obj: ModelType) -> ModelType:
        if hasattr(obj, "org_id") and not getattr(obj, "org_id", None):
            raise TypeError("obj.org_id must be set before creating")
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType, data: dict) -> ModelType:
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, org_id: str, id: str) -> bool:
        obj = await self.get(org_id, id)
        if obj is None:
            return False
        await self.db.delete(obj)
        try:
            await self.db.commit()
        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError(
                f"cannot delete {self.model.__name__}: still referenced by another record"
            ) from e
        return True
