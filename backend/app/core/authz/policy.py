from __future__ import annotations

from app.models.role import Role

# ---------------------------------------------------------------------------
# Static permission matrix (in-code, not a DB table).
# Every resource:action pair below is checked via require_permission() in the
# FastAPI dependency chain.  Role.owner gets "*" (everything).
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
    Role.owner: {"*"},
    Role.admin: {
        "orgs:read",
        "orgs:manage",
        "providers:manage",
        "providers:read",
        "mcp:manage",
        "mcp:read",
        "models:manage",
        "models:read",
        "agents:*",
        "workflows:*",
        "tools:*",
        "files:manage",
        "files:read",
        "sessions:*",
        "usage:read",
        "audit:read",
        "approvals:read",
        "approvals:decide",
        "evaluations:read",
        "evaluations:manage",
        "evaluations:run",
        "quota:read",
        "quota:usage",
    },
    Role.developer: {
        "agents:create",
        "agents:read",
        "agents:run",
        "agents:update",
        "agents:delete",
        "agents:publish",
        "workflows:create",
        "workflows:read",
        "workflows:run",
        "workflows:update",
        "workflows:delete",
        "tools:use:safe",
        "tools:use:read",
        "tools:use:write",
        "tools:use:execute",
        "tools:use:network",
        "files:manage",
        "files:read",
        "sessions:*",
        "usage:read",
        "models:read",
        "providers:read",
        "evaluations:read",
        "evaluations:manage",
        "evaluations:run",
        "quota:usage",
    },
    Role.viewer: {
        "agents:read",
        "workflows:read",
        "usage:read",
        "sessions:read",
        "models:read",
        "providers:read",
        "orgs:read",
        "evaluations:read",
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

