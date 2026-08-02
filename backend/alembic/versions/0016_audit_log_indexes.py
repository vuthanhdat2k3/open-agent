"""index audit_logs for tenant-scoped time and action queries

M13 audits every tool call and guardrail decision, so this table grows
orders of magnitude faster than when only control-plane mutations were
recorded. Both indexes are composite and org-first because every read path
is tenant-scoped: the M15 trace sampler filters by (org_id, action) and the
compliance export filters by (org_id, created_at).

Revision ID: 0016_audit_log_indexes
Revises: 0015_workspace_artifacts
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op

revision: str = "0016_audit_log_indexes"
down_revision: str | None = "0015_workspace_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_org_created",
        "audit_logs",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_audit_logs_org_action",
        "audit_logs",
        ["org_id", "action"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_org_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
