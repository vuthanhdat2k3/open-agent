from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.channel import ChannelConnection
from app.models.organization import Organization
from app.services.channel_service import ChannelService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_include_all_sees_shared_and_every_members_personal_connections(
    async_session_factory,
):
    async with async_session_factory() as db:
        org = Organization(id="org-vis-1", name="Vis Org", slug="vis-org-1")
        db.add(org)
        db.add_all(
            [
                ChannelConnection(
                    id="conn-shared",
                    org_id="org-vis-1",
                    created_by_user_id=None,
                    provider="telegram",
                    bot_token_enc="enc",
                    bot_username="shared_bot",
                ),
                ChannelConnection(
                    id="conn-personal-a",
                    org_id="org-vis-1",
                    created_by_user_id="user-a",
                    provider="telegram",
                    bot_token_enc="enc",
                    bot_username="a_bot",
                ),
                ChannelConnection(
                    id="conn-personal-b",
                    org_id="org-vis-1",
                    created_by_user_id="user-b",
                    provider="discord",
                    bot_token_enc="enc",
                    bot_username="b_bot",
                ),
            ]
        )
        await db.commit()

        service = ChannelService(db)

        admin_view = await service.list_connections("org-vis-1", include_all=True)
        assert {c.id for c in admin_view} == {"conn-shared", "conn-personal-a", "conn-personal-b"}

        user_a_view = await service.list_connections("org-vis-1", owner_user_id="user-a")
        assert {c.id for c in user_a_view} == {"conn-personal-a"}

        shared_only_view = await service.list_connections("org-vis-1")
        assert {c.id for c in shared_only_view} == {"conn-shared"}
