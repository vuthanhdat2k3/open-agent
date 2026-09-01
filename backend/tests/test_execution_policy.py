from __future__ import annotations

import pytest

from app.core.execution_policy import (
    ExecutionPolicy,
    normalize_execution_policy,
    policy_allows_tier,
    policy_requires_approval,
)
from app.core.tools.authorization import (
    ToolAuthorizationError,
    authorize_tool_call,
    build_tool_authorization,
)
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolSpec

ORG_ID = "org-execution-policy-tests"


def _spec(tier: RiskTier, *, requires_approval: bool = False) -> ToolSpec:
    async def _run(args: dict, ctx) -> str:
        return "ok"

    return ToolSpec(
        name=f"{tier.value}_tool",
        description="policy test tool",
        input_schema={"type": "object"},
        run=_run,
        risk_tier=tier,
        requires_approval=requires_approval,
    )


def _context(
    policy: ExecutionPolicy | None,
    *,
    allowed_tiers: list[str] | None = None,
):
    return build_tool_authorization(
        org_id=ORG_ID,
        user_id=None,
        user_role=None,
        agent_id="agent-policy-test",
        allowed_risk_tiers=allowed_tiers or [RiskTier.safe.value],
        execution_policy=policy,
        run_id="run-policy-test",
        principal_type="system",
    )


def test_normalize_execution_policy_defaults_to_manual() -> None:
    assert normalize_execution_policy(None) is ExecutionPolicy.manual
    assert normalize_execution_policy("unknown") is ExecutionPolicy.manual
    assert normalize_execution_policy("full-access") is ExecutionPolicy.full_access


def test_read_only_allows_non_mutating_tiers_and_blocks_mutation() -> None:
    assert policy_allows_tier(ExecutionPolicy.read_only, RiskTier.safe.value)
    assert policy_allows_tier(ExecutionPolicy.read_only, RiskTier.read.value)
    assert policy_allows_tier(ExecutionPolicy.read_only, RiskTier.network.value)
    assert not policy_allows_tier(ExecutionPolicy.read_only, RiskTier.write.value)
    assert not policy_allows_tier(ExecutionPolicy.read_only, RiskTier.execute.value)
    assert not policy_allows_tier(ExecutionPolicy.read_only, RiskTier.dangerous.value)

    with pytest.raises(ToolAuthorizationError, match="read-only"):
        authorize_tool_call(
            _spec(RiskTier.write),
            {},
            context=_context(ExecutionPolicy.read_only),
            runtime_org_id=ORG_ID,
        )


def test_manual_requires_approval_for_mutating_tiers() -> None:
    spec = _spec(RiskTier.write)
    assert policy_requires_approval(ExecutionPolicy.manual, spec)
    with pytest.raises(ToolAuthorizationError, match="requires an approved request"):
        authorize_tool_call(
            spec,
            {},
            context=_context(ExecutionPolicy.manual),
            runtime_org_id=ORG_ID,
        )


def test_full_access_runs_without_approval_pause() -> None:
    spec = _spec(RiskTier.dangerous, requires_approval=True)
    assert not policy_requires_approval(ExecutionPolicy.full_access, spec)
    authorize_tool_call(
        spec,
        {},
        context=_context(ExecutionPolicy.full_access),
        runtime_org_id=ORG_ID,
    )


def test_legacy_context_still_uses_agent_risk_tiers() -> None:
    with pytest.raises(ToolAuthorizationError, match="not enabled for this agent"):
        authorize_tool_call(
            _spec(RiskTier.write),
            {},
            context=_context(None, allowed_tiers=[RiskTier.safe.value]),
            runtime_org_id=ORG_ID,
        )


def test_build_execution_policy_context() -> None:
    from app.core.execution_policy import build_execution_policy_context

    ro = build_execution_policy_context(ExecutionPolicy.read_only)
    assert "[Execution Policy: read-only]" in ro
    assert "blocked" in ro

    fa = build_execution_policy_context(ExecutionPolicy.full_access)
    assert "[Execution Policy: full-access]" in fa
    assert "autonomous full access" in fa

    ma = build_execution_policy_context(ExecutionPolicy.manual)
    assert "[Execution Policy: manual-approval]" in ma
    assert "require user confirmation" in ma
