"""Add the Gmail monitor as a first-class automation template."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0041_gmail_monitor_template"
down_revision = "0040_workflow_occurrences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = datetime.utcnow()
    templates = sa.table(
        "workflow_templates",
        sa.column("id", sa.String), sa.column("key", sa.String), sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )
    versions = sa.table(
        "workflow_template_versions",
        sa.column("id", sa.String), sa.column("template_id", sa.String), sa.column("version", sa.Integer),
        sa.column("name", sa.String), sa.column("description", sa.String), sa.column("outcome", sa.String),
        sa.column("category", sa.String), sa.column("icon", sa.String), sa.column("required_integrations", sa.JSON),
        sa.column("optional_integrations", sa.JSON), sa.column("default_schedule_label", sa.String),
        sa.column("cost_tier", sa.String), sa.column("estimated_cost_usd", sa.JSON), sa.column("side_effect_policy", sa.String),
        sa.column("recommendation_reason_code", sa.String), sa.column("published_at", sa.DateTime), sa.column("created_at", sa.DateTime),
    )
    op.bulk_insert(templates, [{"id": "workflow-template-07", "key": "gmail_monitor_and_triage", "status": "published", "created_at": now, "updated_at": now}])
    op.bulk_insert(versions, [{
        "id": "workflow-template-version-07", "template_id": "workflow-template-07", "version": 1,
        "name": "Monitor and triage new Gmail",
        "description": "Read new Gmail asynchronously, ignore spam, summarize useful mail, and route customer or meeting messages.",
        "outcome": "Every new email is safely classified and routed without rescanning the mailbox on restart.",
        "category": "daily_planning", "icon": "mail-search", "required_integrations": ["gmail"], "optional_integrations": ["google_calendar"],
        "default_schedule_label": "When a new email arrives", "cost_tier": "low", "estimated_cost_usd": {"per_run_max": "0.05"},
        "side_effect_policy": "approval_required", "recommendation_reason_code": "CONNECTED_GMAIL", "published_at": now, "created_at": now,
    }])


def downgrade() -> None:
    op.execute("DELETE FROM workflow_template_versions WHERE id = 'workflow-template-version-07'")
    op.execute("DELETE FROM workflow_templates WHERE id = 'workflow-template-07'")
