from __future__ import annotations

from app.models.role import Role

# ---------------------------------------------------------------------------
# Static permission matrix (in-code, not a DB table).
# Every resource:action pair below is checked via require_permission() in the
# FastAPI dependency chain.
#
# Two-role model: admin configures/operates the product; user consumes it.
# Admin gets "*" (everything, including every current and future permission
# string) rather than an enumerated list - there is no "trusted but slightly
# less than admin" tier to reason about anymore.
#
# User's permissions are deliberately narrow: chat with the org's primary
# (orchestrator-kind) agent, run already-published workflows, see their own
# usage/quota/data. Everything that shapes the product for every user
# (agents, workflows authoring, providers, models, MCP,
# members, evaluations, audit, approvals-decide, files write) is admin-only.
#
# Convention: ``<domain>:<action>``
#   domain  = plural noun (agents, workflows, providers, models, mcp, org, …)
#   action  = create | read | update | delete | run | manage | …
#
# ``domain:*`` is a shorthand that matches every action under that domain.
# The matcher logic (``has_permission``) supports glob-like ``*`` prefixes
# and suffixes.
# ---------------------------------------------------------------------------

PERMISSIONS: dict[Role, set[str]] = {
    Role.admin: {"*"},
    Role.user: {
        "agents:read",
        "agents:run",
        "workflows:read",
        "workflows:run",
        "workflows:install",
        "tools:use:safe",
        "tools:use:read",
        "tools:use:write",
        "tools:use:execute",
        "tools:use:network",
        "files:read",
        "sessions:*",
        "usage:read",
        "approvals:read",
        "quota:usage",
        "models:read",
        "ci:read",
        "ci:personal:manage",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    """Check whether *role* has a specific *permission* string.

    Supports the ``*`` wildcard:
      - ``"*"`` matches everything.
      - ``"agents:*"`` matches any ``agents:`` action.
      - ``"tools:use:*"`` matches any ``tools:use:`` action.
    """
    allowed = PERMISSIONS.get(role)
    if allowed is None:
        return False
    if "*" in allowed:
        return True
    if permission in allowed:
        return True
    # Glob-like match: domain:*  or  domain:sub:*
    for pattern in allowed:
        if pattern.endswith(":*"):
            prefix = pattern[:-1]  # "agents:"
            if permission.startswith(prefix):
                return True
    return False


def request_has_permission(request: object, permission: str) -> bool:
    """Read the permission resolved by the shared request dependency chain."""
    state = getattr(request, "state", None)
    role = getattr(state, "role", None)
    return has_permission(role, permission) if role is not None else False


def evaluate_permission_intersection(
    user_role: Role,
    permission: str,
    agent_allowed_risk_tiers: list[str] | None = None,
    agent_identity_enabled: bool = True,
) -> bool:
    """Calculates the intersection of User permissions and Agent Identity permissions.

    The effective permission is True ONLY IF both the user role has the required
    permission AND the agent (identity) permits the operation. An agent NEVER
    gains higher privileges than the calling user (User permissions ∩ Agent permissions).
    """
    if not agent_identity_enabled:
        return False

    user_has = has_permission(user_role, permission)
    if not user_has:
        return False

    # If checking tool risk tier permission ("tools:use:<tier>")
    if permission.startswith("tools:use:") and agent_allowed_risk_tiers is not None:
        tier = permission.split("tools:use:", 1)[1]
        if tier not in agent_allowed_risk_tiers and "*" not in agent_allowed_risk_tiers:
            return False

    return True

