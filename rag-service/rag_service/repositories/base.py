"""Repository base class."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepo:
    """Base repository holding the async session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
