from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.quota.redis_backend import RedisQuotaBackend
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.quota_service import (
    QuotaService,
    invalidate_monthly_cost_cache,
)

PASSWORD = "Quota-Password-123!"


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
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


def _register(client: TestClient, email: str) -> tuple[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "org_name": email},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["memberships"][0]["org_id"]


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}


@pytest.mark.asyncio
async def test_sliding_window_is_atomic_and_tenant_scoped() -> None:
    redis = from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    prefix = f"test:quota:{uuid.uuid4().hex}"
    backend_one = RedisQuotaBackend(redis, prefix)
    backend_two = RedisQuotaBackend(redis, prefix)
    try:
        first, second = await asyncio.gather(
            backend_one.sliding_window("org-a", "requests", 2),
            backend_two.sliding_window("org-a", "requests", 2),
        )
        assert first.allowed and second.allowed
        assert not (
            await backend_one.sliding_window("org-a", "requests", 2)
        ).allowed
        assert (
            await backend_one.sliding_window("org-b", "requests", 2)
        ).allowed
    finally:
        keys = [key async for key in redis.scan_iter(f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.asyncio
async def test_concurrent_lease_release_and_ttl() -> None:
    redis = from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    prefix = f"test:quota:{uuid.uuid4().hex}"
    backend = RedisQuotaBackend(redis, prefix)
    try:
        first = await backend.acquire_lease("org", 1, ttl_seconds=1)
        assert first.allowed and first.token
        assert not (await backend.acquire_lease("org", 1, ttl_seconds=1)).allowed
        await backend.release_lease("org", first.token)
        replacement = await backend.acquire_lease("org", 1, ttl_seconds=1)
        assert replacement.allowed
        await asyncio.sleep(1.1)
        assert (await backend.acquire_lease("org", 1, ttl_seconds=1)).allowed
    finally:
        keys = [key async for key in redis.scan_iter(f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.asyncio
async def test_usage_write_invalidates_monthly_cost_cache() -> None:
    redis = from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    org_id = uuid.uuid4().hex
    key = QuotaService._cost_cache_key(org_id)
    try:
        await redis.set(key, "12.5", ex=30)
        await invalidate_monthly_cost_cache(org_id)
        assert await redis.get(key) is None
    finally:
        await redis.delete(key)
        await redis.aclose()


def test_quota_api_rbac_headers_and_observe_mode(client: TestClient) -> None:
    owner_token, org_id = _register(client, "quota-owner@example.com")
    owner_headers = _headers(owner_token, org_id)
    quota = client.get(f"/api/orgs/{org_id}/quota", headers=owner_headers)
    assert quota.status_code == 200
    assert quota.headers["RateLimit-Limit"] == "600"

    viewer_token, _ = _register(client, "quota-viewer@example.com")
    invited = client.post(
        f"/api/orgs/{org_id}/members",
        headers=owner_headers,
        json={"email": "quota-viewer@example.com", "role": "viewer"},
    )
    assert invited.status_code == 201
    assert (
        client.get(
            f"/api/orgs/{org_id}/quota",
            headers=_headers(viewer_token, org_id),
        ).status_code
        == 403
    )

    updated = client.put(
        f"/api/orgs/{org_id}/quota",
        headers=owner_headers,
        json={"requests_per_minute": 1, "enforcement_mode": "observe"},
    )
    assert updated.status_code == 200, updated.text
    for _ in range(3):
        observed = client.get(
            f"/api/orgs/{org_id}/quota/usage", headers=owner_headers
        )
        assert observed.status_code == 200
        assert observed.headers["RateLimit-Remaining"] == "0"


def test_resource_quota_rejects_next_agent(client: TestClient) -> None:
    token, org_id = _register(client, "quota-resource@example.com")
    headers = _headers(token, org_id)
    provider = client.post(
        "/api/providers",
        headers=headers,
        json={
            "key": "quota-provider",
            "name": "Quota Provider",
            "base_url": "http://localhost:9999/v1",
            "api_key": "test",
        },
    )
    model = client.post(
        "/api/models",
        headers=headers,
        json={
            "provider_id": provider.json()["id"],
            "name": "quota-model",
            "display_name": "Quota Model",
        },
    )
    update = client.put(
        f"/api/orgs/{org_id}/quota",
        headers=headers,
        json={"max_agents": 1},
    )
    assert update.status_code == 200
    first = client.post(
        "/api/agents",
        headers=headers,
        json={"name": "First", "model_id": model.json()["id"]},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/agents",
        headers=headers,
        json={"name": "Second", "model_id": model.json()["id"]},
    )
    assert second.status_code == 429

    budget = client.put(
        f"/api/orgs/{org_id}/quota",
        headers=headers,
        json={"monthly_cost_usd": 0},
    )
    assert budget.status_code == 200
    blocked_run = client.post(
        "/api/chat",
        headers=headers,
        json={"agent_id": first.json()["id"], "message": "hello", "stream": False},
    )
    assert blocked_run.status_code == 429
    assert blocked_run.json()["detail"] == "monthly cost limit reached"


def test_redis_outage_fails_open_for_reads_and_closed_for_writes(
    client: TestClient,
) -> None:
    token, org_id = _register(client, "quota-outage@example.com")
    headers = _headers(token, org_id)
    settings = get_settings()
    original_url = settings.redis_url
    settings.redis_url = "redis://127.0.0.1:1/0"
    try:
        assert client.get("/api/agents", headers=headers).status_code == 200
        blocked = client.post(
            "/api/providers",
            headers=headers,
            json={
                "key": "offline",
                "name": "Offline",
                "base_url": "http://localhost:9999/v1",
                "api_key": "test",
            },
        )
        assert blocked.status_code == 503
        assert blocked.json()["detail"] == "quota service unavailable"
    finally:
        settings.redis_url = original_url
