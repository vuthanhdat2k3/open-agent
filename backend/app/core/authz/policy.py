from __future__ import annotations

from dataclasses import dataclass

from app.models.role import Role

# ---------------------------------------------------------------------------
# Static permission matrix (in-code, not a DB table).
# Every resource:action pair below is checked via require_permission() in the
# FastAPI dependency chain.
#
# Four-role model:
#   platform_admin and org_admin get "*" - full control of the platform
#   (platform_admin) or the org (org_admin), including every current and
#   future permission string. Route-level permissions must still be declared
#   explicitly below (see the update block) so the audit list stays complete.
#   operator runs and edits the product's artifacts but does not manage the
#   org (no orgs:*, models:manage, files:manage, admin:email-intelligence).
#   user consumes: chat with the org's primary (orchestrator-kind) agent, run
#   already-published workflows, manage their OWN customer-intelligence
#   connections (ci:personal:manage), see their own usage/quota/data.
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
    Role.platform_admin: {"*"},
    Role.org_admin: {"*"},
    Role.operator: {
        "agents:*", "models:*", "providers:*", "workflows:*", "mcp:*", "files:*",
        "evaluations:*", "usage:*", "debug:*", "sessions:*", "approvals:*", "ci:*",
        "channels:*",
        "tools:use:*", "quota:usage",
    },
    Role.user: {
        "agents:read",
        "agents:run",
        "workflows:read",
        "workflows:run",
        "workflows:install",
        "workflows:create",
        "workflows:update",
        "workflows:delete",
        "tools:use:safe",
        "tools:use:read",
        "tools:use:write",
        "tools:use:execute",
        "tools:use:network",
        "files:read",
        "files:write",
        "sessions:*",
        "usage:read",
        "approvals:read",
        "quota:usage",
        "models:read",
        "ci:read",
        "ci:personal:manage",
        "channels:read",
        "channels:personal:manage",
    },
}

# Permissions used by route-level decisions must be declared here even when
# they are currently reachable only through the admin wildcard. This keeps the
# policy auditable before additional org roles are introduced.
PERMISSIONS[Role.org_admin].update({
    "agents:manage",
    "agents:publish:force",
    "approvals:manage",
    "ci:organization:read",
    "admin:email-intelligence",
})


@dataclass(frozen=True)
class PrincipalContext:
    """The authorization result for one authenticated org request."""

    user_id: str
    role: Role
    principal_type: str = "human"
    organization_id: str | None = None
    membership_id: str | None = None
    principal_id: str | None = None
    session_id: str | None = None

    def allows(self, permission: str) -> bool:
        return has_permission(self.role, permission)

    @property
    def effective_principal_id(self) -> str:
        return self.principal_id or self.user_id

    @property
    def owner_user_id(self) -> str | None:
        return self.user_id if self.role == Role.user else None


def has_permission(role: Role | str, permission: str) -> bool:
    """Check whether *role* has a specific *permission* string.

    Supports the ``*`` wildcard:
      - ``"*"`` matches everything.
      - ``"agents:*"`` matches any ``agents:`` action.
      - ``"tools:use:*"`` matches any ``tools:use:`` action.
    """
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False
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

