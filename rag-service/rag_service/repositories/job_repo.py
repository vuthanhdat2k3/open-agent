"""Ingest job repository — pure SQLAlchemy async access, no business logic."""

from __future__ import annotations

from sqlalchemy import select

from rag_service.models import IngestJob
from rag_service.repositories.base import BaseRepo


class JobRepo(BaseRepo):
    async def create(self, **fields: object) -> IngestJob:
        job = IngestJob(**fields)  # type: ignore[arg-type]
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, id: str) -> IngestJob | None:  # noqa: A002
        result = await self.session.execute(
            select(IngestJob).where(IngestJob.id == id)
        )
        return result.scalar_one_or_none()

    async def update(self, job: IngestJob, **fields: object) -> None:
        for key, value in fields.items():
            setattr(job, key, value)
        await self.session.flush()
