from __future__ import annotations

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base, utc_now
from app.db.session import get_db
from app.main import app
from app.models.agent import Agent
from app.models.model import Model
from app.models.provider import Provider
from app.models.task import Task


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


def _register(client: TestClient) -> tuple[str, str]:
    resp = client.post(
        "/api/auth/register",
        json={"email": "debug-task@test.com", "password": "Secret123!", "org_name": "DebugOrg"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    return token, me.json()["memberships"][0]["org_id"]


def test_debug_tasks_endpoint_returns_tree(client: TestClient, async_session_factory) -> None:
    token, org_id = _register(client)

    async def _seed() -> str:
        async with async_session_factory() as session:
            provider = Provider(org_id=org_id, key="debug", name="Debug", base_url="http://debug")
            session.add(provider)
            await session.commit()
            await session.refresh(provider)

            model = Model(
                org_id=org_id,
                provider_id=provider.id,
                name="debug-model",
                display_name="Debug Model",
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)

            agent = Agent(org_id=org_id, name="Debug Agent", model_id=model.id)
            session.add(agent)
            await session.commit()
            await session.refresh(agent)

            root = Task(
                org_id=org_id,
                root_run_id="debug-root",
                agent_id=agent.id,
                goal="root",
                status="succeeded",
                depth=0,
                started_at=utc_now(),
                finished_at=utc_now(),
            )
            session.add(root)
            await session.commit()
            await session.refresh(root)

            child = Task(
                org_id=org_id,
                parent_task_id=root.id,
                root_run_id="debug-root",
                agent_id=agent.id,
                goal="child",
                status="succeeded",
                depth=1,
                started_at=utc_now(),
                finished_at=utc_now(),
            )
            session.add(child)
            await session.commit()
            return root.root_run_id

    root_run_id = anyio.run(_seed)
    resp = client.get(
        f"/api/debug/tasks/{root_run_id}",
        headers={"Authorization": f"Bearer {token}", "X-Org-Id": org_id},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["root_run_id"] == "debug-root"
    assert body["tasks"][0]["goal"] == "root"
    assert body["tasks"][0]["children"][0]["goal"] == "child"

