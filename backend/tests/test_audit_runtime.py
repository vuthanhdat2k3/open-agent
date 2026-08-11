"""M13 — runtime audit trail.

M7 audited only the ``dangerous`` risk tier, so an operator reading the
audit trail could not tell an ordinary tool call, a redacted secret or a
refused run from silence. These tests pin the expanded coverage and, just
as importantly, pin what must NOT reach the audit trail: secret values and
attacker-controlled payloads.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import agent_loop as agent_loop_module
from app.core.agent_loop import _agent_stream
from app.core.observability.audit import log_action
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.db.base import Base
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider

# Synthetic, non-functional — shaped like a key so the redactor fires.
SECRET_VALUE = "sk-livetestsecret0123456789abcdefghij"


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(session: AsyncSession, *, tools: list[str], tiers: list[str]) -> Agent:
    org = Organization(name="Audit Org", slug="audit-org")
    session.add(org)
    await session.commit()
    await session.refresh(org)

    provider = Provider(
        org_id=org.id, name="OpenAI", key="openai", base_url="http://x", api_key="k"
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    model = Model(
        org_id=org.id,
        provider_id=provider.id,
        name="gpt-4o-mini",
        display_name="GPT-4o mini",
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)

    agent = Agent(
        org_id=org.id,
        name="auditor",
        model_id=model.id,
        tools=tools,
        allowed_risk_tiers=tiers,
        max_iterations=3,
        temperature=0.0,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


def _tool_call_delta(name: str, arguments: str) -> dict:
    """Mimics the normalized tool-call delta shape every driver yields."""
    return {"index": 0, "id": "call-1", "name": name, "arguments": arguments}


def _fake_stream(tool_name: str | None):
    """stream() replacement: one tool call, then a final answer."""
    calls = {"n": 0}

    async def stream(self, messages, tools=None, temperature=0.7):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1 and tool_name:
            yield {"type": "tool_calls", "tool_calls": [_tool_call_delta(tool_name, "{}")]}
        else:
            yield {"type": "content", "text": "done"}
        yield {
            "type": "usage",
            "usage": {"input_tokens": 11, "output_tokens": 3},
            "estimated": False,
            "finish_reasons": ["stop"],
        }

    return stream


def _probe(name: str, tier: RiskTier, output: str) -> None:
    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        return output

    register(
        ToolSpec(
            name=name,
            description="probe",
            input_schema={"type": "object", "properties": {}},
            run=_run,
            risk_tier=tier,
        )
    )


async def _drain(agent: Agent, db: AsyncSession, message: str = "go") -> None:
    async for _ in _agent_stream(agent, message, db, 0, None):
        pass


async def _actions(db: AsyncSession, org_id: str) -> list[str]:
    res = await db.execute(select(AuditLog).where(AuditLog.org_id == org_id))
    return [r.action for r in res.scalars().all()]


async def _rows(db: AsyncSession, org_id: str, action: str) -> list[AuditLog]:
    res = await db.execute(
        select(AuditLog).where(AuditLog.org_id == org_id, AuditLog.action == action)
    )
    return list(res.scalars().all())


# --------------------------------------------------------------------------- #
# log_action contract
# --------------------------------------------------------------------------- #
async def test_deferred_commit_defers_until_caller_flushes(session_factory) -> None:
    """commit=False must not hit the database on its own."""
    async with session_factory() as db:
        org = Organization(name="Deferred", slug="deferred")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        org_id = org.id

        await log_action(
            db, org_id=org_id, action="tool.executed", resource_type="tool", commit=False
        )

    async with session_factory() as verify:
        assert await _actions(verify, org_id) == []

    async with session_factory() as db:
        await log_action(
            db, org_id=org_id, action="tool.executed", resource_type="tool", commit=False
        )
        await db.commit()

    async with session_factory() as verify:
        assert await _actions(verify, org_id) == ["tool.executed"]


# --------------------------------------------------------------------------- #
# Tool auditing
# --------------------------------------------------------------------------- #
async def test_ordinary_tool_call_is_audited(session_factory, monkeypatch) -> None:
    """M7 recorded only the dangerous tier; every call is evidence now."""
    _probe("audit_probe_safe", RiskTier.safe, "harmless output")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("audit_probe_safe"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["audit_probe_safe"], tiers=["safe"])
        await _drain(agent, db)
        actions = await _actions(db, agent.org_id)

    assert "tool.executed" in actions
    assert "tool.dangerous.executed" not in actions


async def test_dangerous_tier_keeps_its_legacy_row(session_factory, monkeypatch) -> None:
    """Existing dashboards and alerts match on tool.dangerous.executed."""
    _probe("audit_probe_danger", RiskTier.dangerous, "ok")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("audit_probe_danger"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["audit_probe_danger"], tiers=["safe", "dangerous"])
        await _drain(agent, db)
        actions = await _actions(db, agent.org_id)

    assert "tool.executed" in actions
    assert "tool.dangerous.executed" in actions


# --------------------------------------------------------------------------- #
# Guardrail auditing — and what must never be recorded
# --------------------------------------------------------------------------- #
async def test_secret_redaction_is_audited_without_leaking_the_secret(
    session_factory, monkeypatch
) -> None:
    """Redaction is pointless if the audit trail keeps the secret."""
    _probe(
        "audit_probe_secret",
        RiskTier.safe,
        f"here is the key {SECRET_VALUE} do not leak it",
    )
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("audit_probe_secret"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["audit_probe_secret"], tiers=["safe"])
        await _drain(agent, db)
        rows = await _rows(db, agent.org_id, "guardrail.secret_redacted")
        res = await db.execute(select(AuditLog).where(AuditLog.org_id == agent.org_id))
        all_rows = list(res.scalars().all())

    assert rows, "secret redaction must be audited"
    assert rows[0].metadata_.get("count", 0) >= 1
    assert "kinds" in rows[0].metadata_
    for row in all_rows:
        assert SECRET_VALUE not in str(row.metadata_)


async def test_risk_tier_denial_is_audited(session_factory, monkeypatch) -> None:
    """A refused run must be distinguishable from a crash."""
    _probe("audit_probe_denied", RiskTier.dangerous, "should never execute")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("audit_probe_denied"))

    async with session_factory() as db:
        agent = await _seed(db, tools=["audit_probe_denied"], tiers=["safe"])
        await _drain(agent, db)
        rows = await _rows(db, agent.org_id, "guardrail.risk_tier_denied")

    assert rows, "a blocked tool must leave an audit trail"
    assert rows[0].metadata_["required_tier"] == "dangerous"
    assert rows[0].metadata_["allowed_tiers"] == ["safe"]


async def test_audit_rows_stay_scoped_to_the_running_org(session_factory, monkeypatch) -> None:
    _probe("audit_probe_tenant", RiskTier.safe, "ok")
    monkeypatch.setattr(agent_loop_module.LLMClient, "stream", _fake_stream("audit_probe_tenant"))

    async with session_factory() as db:
        other = Organization(name="Other", slug="other-org")
        db.add(other)
        await db.commit()
        await db.refresh(other)

        agent = await _seed(db, tools=["audit_probe_tenant"], tiers=["safe"])
        await _drain(agent, db)

        assert await _actions(db, other.id) == []
        assert await _actions(db, agent.org_id) != []
