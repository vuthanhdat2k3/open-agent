from enum import Enum


class Role(str, Enum):  # noqa: UP042
    # Two-role model: admin configures/operates the product (agents, workflows,
    # providers, models, MCP, integrations, members, approvals-decide); user
    # consumes it (chat with the org's primary agent, run published workflows,
    # see their own data). See docs/superpowers/specs for the RBAC design.
    admin = "admin"
    user = "user"
