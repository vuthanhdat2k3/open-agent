from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.providers.driver import ModelInfo
from app.core.providers.driver import TestResult as DriverTestResult
from app.core.providers.templates import get_templates
from app.db.base import Base, utc_now
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.services.model_discovery_service import DiscoveryResult, ModelDiscoveryService
from app.services.model_service import ModelService
from app.services.provider_service import ProviderService


@pytest.fixture
async def provider_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        db.add(Organization(id="org-provider", name="Provider Org", slug="provider-org"))
        await db.commit()
    yield factory
    await engine.dispose()


async def _success_probe(*_args, **_kwargs) -> DiscoveryResult:
    return DiscoveryResult(
        test=DriverTestResult(True, 12, "connected"),
        models=[ModelInfo("demo-model", "Demo model", context_window=16384, supports_tools=True)],
        discovery_success=True,
        attempted_at=utc_now(),
    )


@pytest.mark.asyncio
async def test_template_create_is_secret_safe_idempotent_and_disabled(
    provider_session_factory, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ModelDiscoveryService, "probe", _success_probe)
    async with provider_session_factory() as db:
        service = ProviderService(db)
        first = await service.create_from_template("org-provider", "openai", "sk-secret-1234")
        first_id = first.id
        assert first.api_key == ""
        assert first.api_key_encrypted
        assert first.api_key_encrypted != "sk-secret-1234"
        assert first.api_key_last4 == "1234"
        assert first.api_key_configured is True

        model = (await db.execute(select(Model).where(Model.provider_id == first.id))).scalar_one()
        assert model.discovered is True
        assert model.enabled is False
        assert model.active is False

        await ModelService(db).update("org-provider", model.id, {"enabled": True})
        second = await service.create_from_template("org-provider", "openai", "sk-new-5678")
        assert second.id == first_id
        refreshed_model = (await db.execute(select(Model).where(Model.id == model.id))).scalar_one()
        assert refreshed_model.enabled is True
        assert refreshed_model.active is True
        assert second.api_key_last4 == "5678"


@pytest.mark.asyncio
async def test_failed_template_test_does_not_persist_provider(
    provider_session_factory, monkeypatch: pytest.MonkeyPatch
):
    async def failed_probe(*_args, **_kwargs):
        return DiscoveryResult(
            test=DriverTestResult(False, 20, "HTTP 401"),
            models=[],
            discovery_success=False,
            discovery_error="HTTP 401",
            attempted_at=utc_now(),
        )

    monkeypatch.setattr(ModelDiscoveryService, "probe", failed_probe)
    async with provider_session_factory() as db:
        with pytest.raises(ValueError, match="HTTP 401"):
            await ProviderService(db).create_from_template("org-provider", "openai", "bad-key")
        assert (await db.execute(select(Provider))).scalars().all() == []


@pytest.mark.asyncio
async def test_discovery_failure_keeps_existing_model_state(
    provider_session_factory, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ModelDiscoveryService, "probe", _success_probe)
    async with provider_session_factory() as db:
        service = ProviderService(db)
        provider = await service.create_from_template("org-provider", "openai", "sk-secret")
        model = (await db.execute(select(Model).where(Model.provider_id == provider.id))).scalar_one()
        await ModelService(db).update("org-provider", model.id, {"enabled": True})
        old_seen = model.last_seen_at

        async def failed_discovery(*_args, **_kwargs):
            return DiscoveryResult(
                test=DriverTestResult(True, 15, "connected"),
                models=[],
                discovery_success=False,
                discovery_error="model discovery timeout",
                attempted_at=utc_now(),
            )

        monkeypatch.setattr(ModelDiscoveryService, "probe", failed_discovery)
        result = await service.test_connection("org-provider", provider.id)
        assert result["ok"] is True
        assert result["discovery_status"] == "failed"
        refreshed = (await db.execute(select(Model).where(Model.id == model.id))).scalar_one()
        assert refreshed.enabled is True
        assert refreshed.active is True
        assert refreshed.last_seen_at == old_seen


@pytest.mark.asyncio
async def test_provider_update_queues_discovery_for_credentials_and_endpoint(
    provider_session_factory, monkeypatch: pytest.MonkeyPatch
):
    queued: list[tuple[str, int]] = []

    async def enqueue(provider_id: str, generation: int) -> str:
        queued.append((provider_id, generation))
        return "job-provider-discovery"

    monkeypatch.setattr("app.services.provider_service.enqueue_provider_discovery", enqueue)
    async with provider_session_factory() as db:
        service = ProviderService(db)
        provider = await service.create(
            "org-provider",
            {
                "key": "custom",
                "name": "Custom",
                "base_url": "https://example.test/v1",
                "api_key": "old-secret",
            },
        )
        queued.clear()

        updated = await service.update("org-provider", provider.id, {"api_key": "new-secret"})
        assert updated.discovery_generation == 1
        assert updated.discovery_status == "pending"
        assert updated.api_key == ""
        assert updated.api_key_encrypted
        assert updated.api_key_last4 == "cret"
        assert queued == [(provider.id, 1)]

        queued.clear()
        renamed = await service.update("org-provider", provider.id, {"name": "Renamed"})
        assert renamed.discovery_generation == 1
        assert queued == []

        queued.clear()
        moved = await service.update(
            "org-provider", provider.id, {"base_url": "https://new.example.test/v1"}
        )
        assert moved.discovery_generation == 2
        assert moved.discovery_status == "pending"
        assert queued == [(provider.id, 2)]


@pytest.mark.asyncio
async def test_provider_update_keeps_pending_when_enqueue_fails(
    provider_session_factory, monkeypatch: pytest.MonkeyPatch
):
    async def enqueue(*_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.services.provider_service.enqueue_provider_discovery", enqueue)
    async with provider_session_factory() as db:
        service = ProviderService(db)
        provider = await service.create(
            "org-provider",
            {
                "key": "custom",
                "name": "Custom",
                "base_url": "https://example.test/v1",
                "api_key": "old-secret",
            },
        )
        updated = await service.update("org-provider", provider.id, {"api_key": "new-secret"})
        assert updated.discovery_generation == 1
        assert updated.discovery_status == "pending"


@pytest.mark.asyncio
async def test_grace_period_recomputes_active(provider_session_factory):
    async with provider_session_factory() as db:
        model = Model(
            org_id="org-provider",
            provider_id="provider-id",
            name="old",
            display_name="Old",
            discovered=True,
            enabled=True,
            active=True,
            source="discovered",
            last_seen_at=utc_now() - timedelta(days=8),
        )
        db.add(model)
        await db.commit()
        service = ModelService(db)
        rows = await service.list("org-provider", with_inactive=True)
        assert rows[0].active is False


def test_registry_contains_requested_templates():
    assert {item.key for item in get_templates()} == {
        "openai",
        "openrouter",
        "ollama",
        "gemini",
        "anthropic",
        "opencode",
        "deepseek",
    }
