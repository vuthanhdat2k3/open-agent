from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth.token_exchange import exchange_token_for_agent, verify_agent_token
from app.core.authz.policy import evaluate_permission_intersection
from app.core.observability.audit import log_action
from app.db.base import Base
from app.models.agent_identity import AgentIdentity
from app.models.audit_log import AuditLog
from app.models.role import Role


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_permission_intersection_user_and_dangerous():
    # "user" role has no tools:use:dangerous permission at all (admin-only tier).
    user_result = evaluate_permission_intersection(
        user_role=Role.user,
        permission="tools:use:dangerous",
        agent_allowed_risk_tiers=["safe", "read", "dangerous"],
    )
    assert user_result is False


@pytest.mark.asyncio
async def test_permission_intersection_user_and_allowed_tiers():
    user_safe = evaluate_permission_intersection(
        user_role=Role.user,
        permission="tools:use:safe",
        agent_allowed_risk_tiers=["safe", "read"],
    )
    assert user_safe is True

    admin_dangerous = evaluate_permission_intersection(
        user_role=Role.org_admin,
        permission="tools:use:dangerous",
        agent_allowed_risk_tiers=["safe", "read"],
    )
    assert admin_dangerous is False


@pytest.mark.asyncio
async def test_token_exchange_rfc8693(async_session_factory):
    async with async_session_factory() as db_session:
        identity = AgentIdentity(
            org_id="org-123",
            agent_id="agent-456",
            subject="agent:org-123:agent-456",
            allowed_audiences=["https://peer.example.com"],
            enabled=True,
        )
        db_session.add(identity)
        await db_session.commit()
        await db_session.refresh(identity)

        token = exchange_token_for_agent(
            user_id="user-789",
            org_id="org-123",
            agent_identity=identity,
            target_audience="https://peer.example.com",
        )

        payload = verify_agent_token(token, expected_audience="https://peer.example.com")
        assert payload["sub"] == "agent:org-123:agent-456"
        assert payload["on_behalf_of_user_id"] == "user-789"
        assert payload["act"]["sub"] == "user-789"
        assert len(payload["delegation_chain"]) == 2
        assert payload["delegation_chain"][0]["id"] == "user-789"
        assert payload["delegation_chain"][1]["identity_id"] == identity.id

        with pytest.raises(ValueError, match="Token audience mismatch"):
            verify_agent_token(token, expected_audience="https://wrong.example.com")


@pytest.mark.asyncio
async def test_audit_log_delegation_chain(async_session_factory):
    async with async_session_factory() as db_session:
        identity = AgentIdentity(
            org_id="org-audit",
            agent_id="agent-audit",
            subject="agent:org-audit:agent-audit",
            allowed_audiences=["*"],
            enabled=True,
        )
        db_session.add(identity)
        await db_session.commit()

        chain = [{"type": "user", "id": "user-a"}, {"type": "agent", "identity_id": identity.id}]
        await log_action(
            db_session,
            org_id="org-audit",
            action="agent.a2a_call",
            resource_type="external_agent",
            actor_user_id="user-a",
            actor_agent_identity_id=identity.id,
            delegation_chain=chain,
        )

        from sqlalchemy import select

        res = await db_session.execute(select(AuditLog).where(AuditLog.org_id == "org-audit"))
        log_entry = res.scalar_one()
        assert log_entry.actor_agent_identity_id == identity.id
        assert log_entry.delegation_chain == chain
