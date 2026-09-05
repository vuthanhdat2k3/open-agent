from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.a2a.card import generate_agent_card
from app.core.tools.builtins import _call_external_agent
from app.core.tools.types import ToolContext
from app.db.base import Base
from app.db.session import get_db
from app.dependencies import get_current_org_id, get_current_user
from app.main import app
from app.models.agent import Agent
from app.models.model import Model
from app.models.provider import Provider
from app.models.user import User
from app.schemas.chat import AgentLoopResult


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def test_user():
    return User(
        id="user-a2a",
        email="a2a@example.com",
        display_name="A2A User",
        is_active=True,
    )


@pytest.fixture
def client(async_session_factory, test_user):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    async def _override_redis():
        yield None

    async def _override_user():
        return test_user

    async def _override_org():
        return "org-a2a"

    from app.core.quota.dependencies import _redis_client

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_redis_client] = _override_redis
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_current_org_id] = _override_org

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_agent_card_opt_in_filtering(async_session_factory):
    async with async_session_factory() as db_session:
        agent_hidden = Agent(
            org_id="org-card",
            name="Private Agent",
            tools=["memory_recall"],
            a2a_exposed=False,
        )
        agent_exposed = Agent(
            org_id="org-card",
            name="Public Agent",
            tools=["web_search"],
            a2a_exposed=True,
        )
        db_session.add_all([agent_hidden, agent_exposed])
        await db_session.commit()

        card = generate_agent_card([agent_hidden, agent_exposed], host_url="https://example.com")
        agents = card.get("agents", [])
        assert len(agents) == 1
        assert agents[0]["id"] == agent_exposed.id
        assert agents[0]["name"] == "Public Agent"
        assert agents[0]["endpoint"] == "https://example.com/api/a2a/tasks"
        assert "web_search" in agents[0]["skills"]


@pytest.mark.asyncio
async def test_a2a_create_task_happy_path(client: TestClient, async_session_factory, test_user):
    from app.models.membership import Membership

    async with async_session_factory() as db:
        user = User(id="user-a2a", email="a2a@example.com", display_name="A2A User", is_active=True)
        mem = Membership(org_id="org-a2a", user_id="user-a2a", role="user")
        prov = Provider(id="p-a2a", org_id="org-a2a", key="test-p", name="test-p", base_url="http://test")
        mdl = Model(id="m-a2a", org_id="org-a2a", provider_id="p-a2a", name="test-m", display_name="test-m")
        agent = Agent(
            id="agent-a2a-1",
            org_id="org-a2a",
            name="Exposed Agent",
            model_id="m-a2a",
            a2a_exposed=True,
        )
        db.add_all([user, mem, prov, mdl, agent])
        await db.commit()

    mock_result = AgentLoopResult(
        content="A2A execution completed successfully",
        cost_usd=0.01,
        latency_ms=120,
    )

    with patch("app.api.v1.routes.a2a.run_agent_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = mock_result
        resp = client.post(
            "/api/a2a/tasks",
            json={"agent_id": "agent-a2a-1", "input": "Perform A2A task"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["output"] == "A2A execution completed successfully"
        assert "task_id" in data


@pytest.mark.asyncio
async def test_agent_card_cross_tenant_isolation(async_session_factory):
    async with async_session_factory() as db:
        agent_org1 = Agent(
            org_id="org-1",
            name="Org 1 Agent",
            a2a_exposed=True,
        )
        agent_org2 = Agent(
            org_id="org-2",
            name="Org 2 Agent",
            a2a_exposed=True,
        )
        db.add_all([agent_org1, agent_org2])
        await db.commit()

    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as local_client:
        resp = local_client.get("/.well-known/agent-card.json?org_id=org-1")
        assert resp.status_code == 200
        agents = resp.json().get("agents", [])
        assert len(agents) == 1
        assert agents[0]["name"] == "Org 1 Agent"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_call_external_agent_requires_identity(async_session_factory):
    async with async_session_factory() as db:
        ctx = ToolContext(
            db=db,
            org_id="org-test",
            agent_id="agent-test",
            user_id="user-test",
        )
        with patch("app.core.tools.builtins.safe_url", return_value="https://external-agent.example.com/api/a2a/tasks"):
            res = await _call_external_agent(
                {
                    "endpoint_url": "https://external-agent.example.com/api/a2a/tasks",
                    "input": "hello",
                },
                ctx,
            )
            assert "error: agent identity not configured" in res


@pytest.mark.asyncio
async def test_a2a_task_execution_with_agent_token_and_audit(async_session_factory):
    from sqlalchemy import select

    from app.core.auth.token_exchange import exchange_token_for_agent
    from app.core.tools.registry import register
    from app.core.tools.risk_tier import RiskTier
    from app.core.tools.types import ToolSpec
    from app.models.agent_identity import AgentIdentity
    from app.models.audit_log import AuditLog
    from app.models.membership import Membership

    async def _dummy_test_tool(args, ctx):
        return "dummy executed"

    register(
        ToolSpec(
            name="test_dummy_tool",
            description="Dummy tool for test",
            input_schema={"type": "object", "properties": {}},
            run=_dummy_test_tool,
            risk_tier=RiskTier.safe,
        )
    )

    async with async_session_factory() as db:
        user = User(id="u-token", email="token@example.com", display_name="Token User", is_active=True)
        mem = Membership(org_id="org-token", user_id="u-token", role="user")
        prov = Provider(id="p-token", org_id="org-token", key="t-p", name="t-p", base_url="http://test", api_key="sk-test-fake")
        mdl = Model(id="m-token", org_id="org-token", provider_id="p-token", name="t-m", display_name="t-m")
        agent = Agent(
            id="agent-token-1",
            org_id="org-token",
            name="Exposed Token Agent",
            model_id="m-token",
            tools=["test_dummy_tool"],
            allowed_risk_tiers=["safe", "network", "read"],
            a2a_exposed=True,
        )
        identity = AgentIdentity(
            id="ident-token-1",
            org_id="org-token",
            agent_id="agent-token-1",
            subject="agent:org-token:agent-token-1",
            allowed_audiences=["*"],
            enabled=True,
        )
        db.add_all([user, mem, prov, mdl, agent, identity])
        await db.commit()

        token = exchange_token_for_agent(
            user_id="u-token",
            org_id="org-token",
            agent_identity=identity,
            target_audience="http://testserver",
        )

    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_get_db

    async def mock_stream(*args, **kwargs):
        yield {
            "type": "tool_calls",
            "tool_calls": [{"index": 0, "id": "tc-1", "name": "test_dummy_tool", "arguments": "{}"}],
        }
        yield {"type": "content", "text": "Task processed via A2A token"}
        yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 10}, "estimated": False}

    with patch("app.core.llm.LLMClient.stream", side_effect=mock_stream), TestClient(app) as test_client:
        resp = test_client.post(
            "/api/a2a/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={"agent_id": "agent-token-1", "input": "Run A2A query"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "succeeded"

    async with async_session_factory() as db:
        res = await db.execute(
            select(AuditLog).where(AuditLog.actor_agent_identity_id == "ident-token-1")
        )
        logs = list(res.scalars().all())
        assert len(logs) >= 1
        tool_executed_log = next(log for log in logs if log.action == "tool.executed")
        assert tool_executed_log.actor_user_id == "u-token"
        assert tool_executed_log.delegation_chain is not None
        assert tool_executed_log.delegation_chain[0]["id"] == "u-token"
        assert tool_executed_log.delegation_chain[1]["identity_id"] == "ident-token-1"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_a2a_guardrail_secret_audit_delegation(async_session_factory):
    from sqlalchemy import select

    from app.core.auth.token_exchange import exchange_token_for_agent
    from app.core.tools.registry import register
    from app.core.tools.risk_tier import RiskTier
    from app.core.tools.types import ToolSpec
    from app.models.agent_identity import AgentIdentity
    from app.models.audit_log import AuditLog
    from app.models.membership import Membership

    async def _secret_tool(args, ctx):
        return "api_key=sk-proj-1234567890123456789012345678901234567890"

    register(
        ToolSpec(
            name="test_secret_tool",
            description="Returns a secret for testing redaction audit",
            input_schema={"type": "object", "properties": {}},
            run=_secret_tool,
            risk_tier=RiskTier.safe,
        )
    )

    async with async_session_factory() as db:
        user = User(id="u-sec", email="sec@example.com", display_name="Sec User", is_active=True)
        mem = Membership(org_id="org-sec", user_id="u-sec", role="user")
        prov = Provider(id="p-sec", org_id="org-sec", key="t-sec", name="t-sec", base_url="http://test", api_key="sk-test-fake")
        mdl = Model(id="m-sec", org_id="org-sec", provider_id="p-sec", name="t-m", display_name="t-m")
        agent = Agent(
            id="agent-sec-1",
            org_id="org-sec",
            name="Exposed Sec Agent",
            model_id="m-sec",
            tools=["test_secret_tool"],
            allowed_risk_tiers=["safe", "network", "read"],
            a2a_exposed=True,
        )
        identity = AgentIdentity(
            id="ident-sec-1",
            org_id="org-sec",
            agent_id="agent-sec-1",
            subject="agent:org-sec:agent-sec-1",
            allowed_audiences=["*"],
            enabled=True,
        )
        db.add_all([user, mem, prov, mdl, agent, identity])
        await db.commit()

        token = exchange_token_for_agent(
            user_id="u-sec",
            org_id="org-sec",
            agent_identity=identity,
            target_audience="http://testserver",
        )

    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = _override_get_db

    async def mock_stream(*args, **kwargs):
        yield {
            "type": "tool_calls",
            "tool_calls": [{"index": 0, "id": "tc-sec", "name": "test_secret_tool", "arguments": "{}"}],
        }
        yield {"type": "content", "text": "Redaction tested"}
        yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 10}, "estimated": False}

    with patch("app.core.llm.LLMClient.stream", side_effect=mock_stream), TestClient(app) as test_client:
        resp = test_client.post(
            "/api/a2a/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={"agent_id": "agent-sec-1", "input": "Test secret redaction"},
        )
        assert resp.status_code == 200

    async with async_session_factory() as db:
        res = await db.execute(
            select(AuditLog).where(
                AuditLog.action == "guardrail.secret_redacted",
                AuditLog.actor_agent_identity_id == "ident-sec-1",
            )
        )
        logs = list(res.scalars().all())
        assert len(logs) >= 1
        assert logs[0].actor_user_id == "u-sec"
        assert logs[0].delegation_chain is not None
        assert logs[0].delegation_chain[0]["id"] == "u-sec"

    app.dependency_overrides.clear()
