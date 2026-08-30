from __future__ import annotations

from enum import Enum
from typing import Any


class ExecutionPolicy(str, Enum):
    """Session-level tool execution policy."""

    read_only = "read-only"
    manual = "manual"
    full_access = "full-access"


# Keep these values independent of app.core.tools so importing models/schemas does
# not trigger the tools package's eager builtin registration.
ALL_RISK_TIERS: frozenset[str] = frozenset(
    {"safe", "read", "write", "execute", "network", "dangerous"}
)
READ_ONLY_RISK_TIERS: frozenset[str] = frozenset({"safe", "read", "network"})
MUTATING_RISK_TIERS: frozenset[str] = ALL_RISK_TIERS - READ_ONLY_RISK_TIERS


def normalize_execution_policy(value: str | ExecutionPolicy | None) -> ExecutionPolicy:
    if isinstance(value, ExecutionPolicy):
        return value
    try:
        return ExecutionPolicy(value or ExecutionPolicy.manual.value)
    except ValueError:
        return ExecutionPolicy.manual


def policy_allows_tier(policy: str | ExecutionPolicy | None, tier: str) -> bool:
    resolved = normalize_execution_policy(policy)
    return tier in READ_ONLY_RISK_TIERS if resolved is ExecutionPolicy.read_only else True


def policy_allows_tool(policy: str | ExecutionPolicy | None, spec: Any) -> bool:
    """Return whether a tool may be offered/executed under the session mode."""
    resolved = normalize_execution_policy(policy)
    tier = getattr(getattr(spec, "risk_tier", None), "value", None) or str(spec.risk_tier)
    if resolved is ExecutionPolicy.read_only:
        return tier in READ_ONLY_RISK_TIERS and not bool(getattr(spec, "requires_approval", False))
    return True


def policy_requires_approval(policy: str | ExecutionPolicy | None, spec: Any) -> bool:
    resolved = normalize_execution_policy(policy)
    if resolved is ExecutionPolicy.full_access:
        return False
    tier = getattr(getattr(spec, "risk_tier", None), "value", None) or str(spec.risk_tier)
    if resolved is ExecutionPolicy.manual and tier in MUTATING_RISK_TIERS:
        return True
    return bool(getattr(spec, "requires_approval", False))


def policy_values() -> tuple[str, ...]:
    return tuple(policy.value for policy in ExecutionPolicy)
