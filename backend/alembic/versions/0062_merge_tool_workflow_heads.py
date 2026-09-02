"""Merge tool-execution-authorization and workflow-template-key branches.

Both ``0061_tool_execution_authorization`` and ``0061_workflow_template_key_and_customized``
branch off ``0060_profile_role_hardening`` independently. With no merge
revision joining them, ``alembic upgrade head`` (or a bare ``stamp``) only
ever advances whichever ``0061`` branch is reached first, silently leaving
the other branch's schema change (here: ``mcp_tools.risk_tier`` /
``mcp_tools.requires_approval``) never applied on databases that got
stamped via the other path. This merge revision - like the existing
``0053_merge_workflow_and_session_heads`` precedent - has no schema changes
of its own; each branch already performs its own DDL.
"""

from collections.abc import Sequence

revision: str = "0062_merge_tool_workflow_heads"
down_revision: str | tuple[str, str] | None = (
    "0061_tool_exec_authz",
    "0061_workflow_template_custom",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
