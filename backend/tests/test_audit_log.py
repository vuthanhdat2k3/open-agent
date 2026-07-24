from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_login_writes_audit_log(client: TestClient, async_session_factory) -> None:
    register = client.post(
        "/api/auth/register",
        json={"email": "audit@test.com", "password": "Secret123!", "org_name": "AuditOrg"},
    )
    assert register.status_code == 201, register.text

    login = client.post(
        "/api/auth/login",
        json={"email": "audit@test.com", "password": "Secret123!"},
    )
    assert login.status_code == 200, login.text

    async def _read_logs():
        async with async_session_factory() as session:
            rows = (await session.execute(select(AuditLog))).scalars().all()
            return rows

    import anyio

    logs = anyio.run(_read_logs)
    assert len(logs) == 1
    assert logs[0].action == "login"
    assert logs[0].resource_type == "user"
    assert logs[0].actor_user_id is not None

