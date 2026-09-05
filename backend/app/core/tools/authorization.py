"""Central authorization for every tool execution.

Tool implementations are intentionally unaware of HTTP/RBAC details.  The
runtime creates a signed-by-convention execution context and the registry
checks it immediately before invoking a tool.  A caller that reaches the
primitive without this context fails closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.core.authz.policy import evaluate_permission_intersection
from app.core.execution_policy import (
    ALL_RISK_TIERS,
    ExecutionPolicy,
    normalize_execution_policy,
    policy_allows_tier,
    policy_requires_approval,
)


class ToolAuthorizationError(PermissionError):
    """Raised when a tool call has no valid execution authorization."""


def tool_args_hash(args: dict[str, Any]) -> str:
    """Return a stable digest for the exact arguments reviewed by an approver."""
    payload = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ToolAuthorizationContext:
    """Immutable authorization snapshot carried by one runtime execution.

    ``principal_type=human`` requires both a user id and a resolved role.  A
    system principal is reserved for explicitly internal jobs/evaluations.
    ``execution_policy`` is the session-level capability mode; the legacy
    ``allowed_risk_tiers`` tuple remains only as a compatibility field for
    non-chat callers.
    """

    org_id: str
    principal_type: str
    principal_id: str
    user_id: str | None
    role: str | None
    agent_id: str | None
    allowed_risk_tiers: tuple[str, ...]
    # ``None`` keeps legacy workflow/evaluation callers on their explicit
    # allowed-risk-tier snapshot. Chat sessions always pass a policy.
    execution_policy: ExecutionPolicy | None = None
    run_id: str | None = None
    approval_id: str | None = None
    approval_status: str | None = None
    approved_tool_name: str | None = None
    approved_args_hash: str | None = None
    replay: bool = False

    @property
    def is_human(self) -> bool:
        return self.principal_type == "human"

    def for_approved_call(
        self,
        *,
        approval_id: str,
        approval_status: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolAuthorizationContext:
        """Return a narrow context for one exact approved invocation."""
        return ToolAuthorizationContext(
            org_id=self.org_id,
            principal_type=self.principal_type,
            principal_id=self.principal_id,
            user_id=self.user_id,
            role=self.role,
            agent_id=self.agent_id,
            allowed_risk_tiers=self.allowed_risk_tiers,
            execution_policy=self.execution_policy,
            run_id=self.run_id,
            approval_id=approval_id,
            approval_status=approval_status,
            approved_tool_name=tool_name,
            approved_args_hash=tool_args_hash(args),
            replay=self.replay,
        )


def build_tool_authorization(
    *,
    org_id: str | None,
    user_id: str | None,
    user_role: str | None,
    agent_id: str | None,
    allowed_risk_tiers: list[str] | tuple[str, ...] | None,
    run_id: str | None,
    principal_type: str | None = None,
    principal_id: str | None = None,
    execution_policy: str | ExecutionPolicy | None = None,
    replay: bool = False,
) -> ToolAuthorizationContext:
    """Build an explicit principal snapshot for an agent/workflow runtime."""
    resolved_type = principal_type or ("human" if user_id else "system")
    resolved_id = principal_id or user_id or "openagent:internal-runtime"
    return ToolAuthorizationContext(
        org_id=org_id or "",
        principal_type=resolved_type,
        principal_id=resolved_id,
        user_id=user_id,
        role=user_role,
        agent_id=agent_id,
        allowed_risk_tiers=tuple(str(t) for t in (allowed_risk_tiers or ())),
        execution_policy=(
            normalize_execution_policy(execution_policy)
            if execution_policy is not None
            else None
        ),
        run_id=run_id,
        replay=replay,
    )


def authorize_tool_call(
    spec: Any,
    args: dict[str, Any],
    *,
    context: ToolAuthorizationContext | None,
    runtime_org_id: str | None,
    check_approval: bool = True,
) -> None:
    """Validate the complete authorization envelope before tool side effects."""
    if context is None:
        raise ToolAuthorizationError("missing tool authorization context")
    if not context.org_id or not runtime_org_id or context.org_id != runtime_org_id:
        raise ToolAuthorizationError("organization context is missing or does not match the tool call")
    if context.replay:
        raise ToolAuthorizationError("replay executions cannot invoke tools")
    if context.principal_type not in {"human", "system", "service"}:
        raise ToolAuthorizationError("unsupported tool execution principal")
    if context.principal_type == "human" and (not context.user_id or not context.role):
        raise ToolAuthorizationError("human tool execution requires user and role context")
    tier = getattr(getattr(spec, "risk_tier", None), "value", None) or str(spec.risk_tier)
    if context.execution_policy is not None:
        if not policy_allows_tier(context.execution_policy, tier):
            raise ToolAuthorizationError(
                f"tool '{spec.name}' is blocked by the '{context.execution_policy.value}' execution policy"
            )
        # The policy replaces agent-level tier capabilities for chat, but it
        # never bypasses the authenticated principal's RBAC permission.
        rbac_tiers = list(ALL_RISK_TIERS)
    else:
        if tier not in context.allowed_risk_tiers and "*" not in context.allowed_risk_tiers:
            raise ToolAuthorizationError(
                f"tool '{spec.name}' requires risk tier '{tier}' which is not enabled for this agent"
            )
        rbac_tiers = list(context.allowed_risk_tiers)
    if context.is_human and not evaluate_permission_intersection(
        context.role or "",
        f"tools:use:{tier}",
        rbac_tiers,
        agent_identity_enabled=True,
    ):
        raise ToolAuthorizationError(
            f"principal is not authorized to use risk tier '{tier}' for tool '{spec.name}'"
        )
    if check_approval and requires_approval(spec, context.execution_policy):
        if context.approval_status != "approved" or not context.approval_id:
            raise ToolAuthorizationError(f"tool '{spec.name}' requires an approved request")
        if context.approved_tool_name != spec.name:
            raise ToolAuthorizationError("approved tool does not match requested tool")
        if context.approved_args_hash != tool_args_hash(args):
            raise ToolAuthorizationError("tool arguments do not match the approved snapshot")


def requires_approval(
    spec: Any, execution_policy: str | ExecutionPolicy | None = None
) -> bool:
    """Return whether a runtime must pause before invoking this tool.

    Risk tier and approval are separate axes: ``risk_tier`` is the
    capability gate (which tiers an agent/role may use at all), while
    ``requires_approval`` is the explicit human-in-the-loop flag a tool
    author opts into. The ``dangerous`` tier does not implicitly require
    approval - it only gets the extra ``tool.dangerous.executed`` audit row.
    """
    if execution_policy is not None:
        return policy_requires_approval(execution_policy, spec)
    return bool(getattr(spec, "requires_approval", False))
