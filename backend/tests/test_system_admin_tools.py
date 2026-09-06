"""Unit tests for System Admin tools and System Administrator Agent Blueprint."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.tools.builtins  # noqa: F401 - Triggers tool registration
from app.core.agents.templates import SYSTEM_AGENT_BLUEPRINTS
from app.core.providers.driver import TestResult
from app.core.tools.registry import BUILTIN_TOOLS
from app.core.tools.types import ToolContext
from app.db.base import Base, gen_id, utc_now
from app.models.model import Model
from app.models.organization import Organization
from app.models.organization_quota import OrganizationQuota
from app.models.provider import Provider
from app.models.user import User
from app.services.model_discovery_service import DiscoveryResult, ModelDiscoveryService


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
async def test_env(async_session_factory):
    async with async_session_factory() as db:
        org = Organization(id=gen_id(), name="ProtonX Enterprise", slug="protonx")
        user = User(id=gen_id(), email="operator@protonx.com", hashed_password="pw", is_active=True)
        db.add(org)
        db.add(user)
        await db.commit()

        # Seed an OpenAI provider
        provider = Provider(
            id=gen_id(),
            org_id=org.id,
            key="openai",
            name="OpenAI Primary",
            base_url="https://api.openai.com/v1",
            template_key="openai",
            is_default=True,
            status="ready",
            discovery_status="completed",
            api_key_last4="1234",
            api_key_encrypted="mock-encrypted",
        )
        db.add(provider)
        await db.commit()

        # Seed models
        m1 = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=provider.id,
            name="gpt-4o-mini",
            display_name="GPT-4o Mini",
            tier="economy",
            active=True,
            enabled=True,
            context_window=128000,
            input_cost_per_1k=0.00015,
            output_cost_per_1k=0.0006,
            supports_tools=True,
            supports_reasoning=False,
            supports_vision=True,
        )
        m2 = Model(
            id=gen_id(),
            org_id=org.id,
            provider_id=provider.id,
            name="gpt-4o",
            display_name="GPT-4o",
            tier="frontier",
            active=True,
            enabled=False,
            context_window=128000,
            input_cost_per_1k=0.005,
            output_cost_per_1k=0.015,
            supports_tools=True,
            supports_reasoning=True,
            supports_vision=True,
        )
        db.add(m1)
        db.add(m2)

        # Seed Quota
        quota = OrganizationQuota(
            org_id=org.id,
            monthly_cost_usd=100.0,
            requests_per_minute=60,
            agent_runs_per_minute=30,
            max_concurrent_runs=5,
            max_agents=10,
            max_workflows=20,
            enforcement_mode="enforce",
        )
        db.add(quota)
        await db.commit()

        yield {
            "org_id": org.id,
            "user_id": user.id,
            "provider_id": provider.id,
            "model_mini_id": m1.id,
            "model_4o_id": m2.id,
            "db": db,
        }


def test_system_admin_agent_blueprint():
    assert "system-admin" in SYSTEM_AGENT_BLUEPRINTS
    bp = SYSTEM_AGENT_BLUEPRINTS["system-admin"]
    assert bp.name == "System Administrator"
    assert bp.kind == "worker"
    assert bp.visibility == "all"
    assert bp.is_pinned_by_default is True
    assert set(bp.allowed_risk_tiers) == {"safe", "read", "write", "network"}

    expected_tools = {
        "system_list_provider_templates",
        "system_list_providers",
        "system_get_provider",
        "system_create_provider",
        "system_update_provider",
        "system_test_provider",
        "system_list_models",
        "system_get_model",
        "system_toggle_model",
        "system_update_model",
        "system_test_model",
        "system_get_model_tiers",
        "system_set_model_tier",
        "system_get_quotas",
        "system_set_quota",
        "get_current_time",
        "save_memory",
        "call_memory",
    }
    assert expected_tools.issubset(set(bp.tools))


@pytest.mark.asyncio
async def test_provider_tools(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # 1. system_list_provider_templates
    tool = BUILTIN_TOOLS["system_list_provider_templates"]
    res = json.loads(await tool.run({}, ctx))
    assert res["count"] > 0
    assert any(t["key"] == "openai" for t in res["templates"])

    # 2. system_list_providers
    tool = BUILTIN_TOOLS["system_list_providers"]
    res = json.loads(await tool.run({}, ctx))
    assert res["count"] == 1
    assert res["providers"][0]["name"] == "OpenAI Primary"
    assert res["providers"][0]["models_count"] == 2

    # 3. system_get_provider
    tool = BUILTIN_TOOLS["system_get_provider"]
    res = json.loads(await tool.run({"provider_id": test_env["provider_id"]}, ctx))
    assert res["provider"]["id"] == test_env["provider_id"]
    assert len(res["provider"]["models"]) == 2

    # 4. system_update_provider
    tool = BUILTIN_TOOLS["system_update_provider"]
    res = json.loads(await tool.run({"provider_id": test_env["provider_id"], "name": "OpenAI Production"}, ctx))
    assert "updated successfully" in res["message"]
    assert res["provider"]["name"] == "OpenAI Production"

    # 5. system_create_provider (mocking probe)
    tool = BUILTIN_TOOLS["system_create_provider"]
    mock_discovery = DiscoveryResult(
        test=TestResult(True, 45, "OK"),
        models=[],
        discovery_success=True,
        used_fallback=True,
        attempted_at=utc_now(),
    )
    with patch.object(ModelDiscoveryService, "probe", return_value=mock_discovery):
        res = json.loads(await tool.run({
            "template_key": "deepseek",
            "name": "DeepSeek API",
            "api_key": "sk-deepseek-test",
        }, ctx))
    assert "created successfully" in res["message"]
    assert res["provider"]["name"] == "DeepSeek API"


@pytest.mark.asyncio
async def test_model_tools(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # 1. system_list_models
    tool = BUILTIN_TOOLS["system_list_models"]
    res = json.loads(await tool.run({}, ctx))
    assert res["count"] == 2

    res_enabled = json.loads(await tool.run({"enabled_only": True}, ctx))
    assert res_enabled["count"] == 1
    assert res_enabled["models"][0]["name"] == "gpt-4o-mini"

    # 2. system_get_model by slug
    tool = BUILTIN_TOOLS["system_get_model"]
    res = json.loads(await tool.run({"model_id": "gpt-4o-mini"}, ctx))
    assert res["model"]["name"] == "gpt-4o-mini"
    assert res["model"]["context_window"] == 128000

    # 3. system_toggle_model
    tool = BUILTIN_TOOLS["system_toggle_model"]
    res = json.loads(await tool.run({"model_id": "gpt-4o", "enabled": True}, ctx))
    assert "enabled" in res["message"]
    assert res["model"]["enabled"] is True

    # 4. system_update_model
    tool = BUILTIN_TOOLS["system_update_model"]
    res = json.loads(await tool.run({
        "model_id": "gpt-4o-mini",
        "display_name": "GPT-4o Mini Turbo",
        "context_window": 200000,
    }, ctx))
    assert "updated successfully" in res["message"]
    assert res["model"]["display_name"] == "GPT-4o Mini Turbo"
    assert res["model"]["context_window"] == 200000


@pytest.mark.asyncio
async def test_model_tier_tools(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # 1. system_get_model_tiers
    tool = BUILTIN_TOOLS["system_get_model_tiers"]
    res = json.loads(await tool.run({}, ctx))
    assert "tier_matrix" in res
    assert "economy" in res["tier_matrix"]

    # 2. system_set_model_tier
    tool = BUILTIN_TOOLS["system_set_model_tier"]
    res = json.loads(await tool.run({"tier": "frontier", "model_id": "gpt-4o-mini"}, ctx))
    assert "Successfully mapped" in res["message"]
    assert res["tier_matrix"]["frontier"]["model_name"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_quota_tools(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # 1. system_get_quotas
    tool = BUILTIN_TOOLS["system_get_quotas"]
    res = json.loads(await tool.run({}, ctx))
    assert res["limits"]["monthly_cost_usd"] == 100.0
    assert res["limits"]["requests_per_minute"] == 60

    # 2. system_set_quota
    tool = BUILTIN_TOOLS["system_set_quota"]
    res = json.loads(await tool.run({
        "monthly_cost_usd": 500.0,
        "requests_per_minute": 120,
        "max_concurrent_runs": 10,
    }, ctx))
    assert "updated successfully" in res["message"]
    assert res["limits"]["monthly_cost_usd"] == 500.0
    assert res["limits"]["requests_per_minute"] == 120
    assert res["limits"]["max_concurrent_runs"] == 10


@pytest.mark.asyncio
async def test_test_connection_and_chat_tools(test_env):
    db = test_env["db"]
    ctx = ToolContext(db=db, org_id=test_env["org_id"], user_id=test_env["user_id"])

    # Mock test_connection
    tool = BUILTIN_TOOLS["system_test_provider"]
    with patch("app.services.provider_service.ProviderService.test_connection", new_callable=AsyncMock) as mock_test:
        mock_test.return_value = {"ok": True, "latency_ms": 120, "model_count": 2, "message": "OK"}
        res = json.loads(await tool.run({"provider_id": test_env["provider_id"]}, ctx))
        assert res["test_result"]["ok"] is True
        assert res["test_result"]["latency_ms"] == 120

    # Mock test_chat
    tool = BUILTIN_TOOLS["system_test_model"]
    with patch("app.services.model_service.ModelService.test_chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {"ok": True, "latency_ms": 250, "sample_response": "OK", "model_name": "gpt-4o-mini"}
        res = json.loads(await tool.run({"model_id": "gpt-4o-mini"}, ctx))
        assert res["test_result"]["ok"] is True
        assert res["test_result"]["sample_response"] == "OK"
