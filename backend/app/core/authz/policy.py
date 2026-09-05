from __future__ import annotations

from dataclasses import dataclass

from app.models.role import Role

# ---------------------------------------------------------------------------
# Static permission matrix (in-code, not a DB table).
# Every resource:action pair below is checked via require_permission() in the
# FastAPI dependency chain.
#
# Four NON-OVERLAPPING roles - each has exactly one job. A user can hold more
# than one role in the same org (Membership allows one row per (org, user,
# role)) when they genuinely need more than one job - e.g. a self-registered
# founder gets both org_admin and operator, since org_admin alone could never
# configure the AI stack it needs to bootstrap (see auth.py::register).
#
#   platform_admin: create/manage organizations and grant org_admin to one.
#   Nothing else, except read-only visibility into every org's AI/ops surface
#   for support ("break-glass") - never write/manage inside a tenant org.
#
#   org_admin: manage org members (assign operator/user - NOT org_admin,
#   that's platform_admin-only via orgs:grant-admin) and org-level system
#   settings (quotas, email-gateway config, audit log). Not involved in AI
#   configuration at all - no agents/models/providers/workflows/mcp/files.
#
#   operator: full AI-stack management (agents/models/providers/workflows/
#   mcp/files/evaluations) - the AI engineer/ops persona. No org-admin
#   surfaces (no orgs:*, admin:email-intelligence).
#
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
    Role.platform_admin: {
        "orgs:create", "orgs:read", "orgs:manage", "orgs:grant-admin",
        # break-glass: read-only visibility into every org's AI/ops surface
        # for support - never write/manage.
        "agents:read", "models:read", "providers:read", "workflows:read",
        "mcp:read", "files:read", "evaluations:read", "usage:read",
        "debug:read", "sessions:read", "approvals:read", "ci:read", "channels:read",
    },
    Role.org_admin: {
        "orgs:read", "orgs:manage", "quota:read", "quota:manage", "quota:usage",
        "admin:email-intelligence", "debug:*", "usage:read",
    },
    Role.operator: {
        "agents:create", "agents:read", "agents:update", "agents:delete",
        "agents:manage", "agents:publish", "agents:publish:force",
        # NO "agents:run" - operator configures AI, does not chat/execute conversations.
        "models:*", "providers:*", "workflows:*", "mcp:*", "files:*",
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


# A user can hold more than one role in the same org (see Membership's
# (org_id, user_id, role) uniqueness). This orders them for DISPLAY only
# (PrincipalContext.role, a UI badge, workflow_catalog.py's admin check) -
# actual authorization always checks the full `roles` set via `allows()`.
ROLE_DISPLAY_PRIORITY: tuple[Role, ...] = (Role.platform_admin, Role.org_admin, Role.operator, Role.user)

# Some single-role call sites downstream of chat (JWT role claim,
# ToolAuthorizationContext.role for tools:use:<tier> checks) can't easily
# consume a role set - for those, prefer whichever role actually grants
# tool use, so a dual-role founder (org_admin, which doesn't, + operator,
# which does) isn't blocked from using the AI stack they can configure.
_TOOL_USE_ROLE_PRIORITY: tuple[Role, ...] = (Role.operator, Role.user, Role.org_admin, Role.platform_admin)


def primary_role(roles: set[Role] | frozenset[Role]) -> Role:
    for candidate in ROLE_DISPLAY_PRIORITY:
        if candidate in roles:
            return candidate
    return Role.user


def tool_use_role(roles: set[Role] | frozenset[Role]) -> Role:
    for candidate in _TOOL_USE_ROLE_PRIORITY:
        if candidate in roles:
            return candidate
    return Role.user


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
    roles: frozenset[Role] = frozenset()

    def __post_init__(self) -> None:
        if not self.roles:
            object.__setattr__(self, "roles", frozenset({self.role}))

    def allows(self, permission: str) -> bool:
        return any(has_permission(role, permission) for role in self.roles)

    @property
    def tool_use_role(self) -> Role:
        return tool_use_role(self.roles)

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

