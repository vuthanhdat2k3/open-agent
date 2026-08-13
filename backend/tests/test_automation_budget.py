from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.customer_intelligence.automation_budget import reserve_daily_budget
from app.models.customer_intelligence import CiAutomationBudget


@pytest.mark.asyncio
async def test_daily_budget_reservation_is_atomic_under_concurrency(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'budget.db'}",
        connect_args={"timeout": 30},
    )
    async with engine.begin() as connection:
        await connection.run_sync(CiAutomationBudget.__table__.create)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def attempt() -> bool:
        async with factory() as db:
            result = await reserve_daily_budget(
                db,
                budget_date="2026-08-13",
                user_id="user-1",
                org_id="org-1",
                user_limit=3,
                org_limit=3,
            )
            if result.reserved:
                await db.commit()
            else:
                await db.rollback()
            return result.reserved

    outcomes = await asyncio.gather(*(attempt() for _ in range(10)))
    assert sum(outcomes) == 3

    async with factory() as db:
        rows = list((await db.scalars(select(CiAutomationBudget))).all())
        assert {(row.scope_type, row.used) for row in rows} == {("USER", 3), ("ORG", 3)}

    await engine.dispose()
