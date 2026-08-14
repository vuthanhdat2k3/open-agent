"""Add the system-owned workflow template catalog and seed the first six templates."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0038_workflow_template_catalog"
down_revision = "0037_agent_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_workflow_templates_key", "workflow_templates", ["key"], unique=False)
    op.create_table(
        "workflow_template_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("outcome", sa.String(length=512), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=False),
        sa.Column("required_integrations", sa.JSON(), nullable=False),
        sa.Column("optional_integrations", sa.JSON(), nullable=False),
        sa.Column("default_schedule_label", sa.String(length=160), nullable=False),
        sa.Column("cost_tier", sa.String(length=16), nullable=False),
        sa.Column("estimated_cost_usd", sa.JSON(), nullable=False),
        sa.Column("side_effect_policy", sa.String(length=48), nullable=False),
        sa.Column("recommendation_reason_code", sa.String(length=96), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["workflow_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version", name="uq_workflow_template_version"),
    )
    op.create_index(
        "ix_workflow_template_versions_template_id",
        "workflow_template_versions",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_template_versions_category",
        "workflow_template_versions",
        ["category"],
        unique=False,
    )

    now = datetime.utcnow()
    templates = sa.table(
        "workflow_templates",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    versions = sa.table(
        "workflow_template_versions",
        sa.column("id", sa.String),
        sa.column("template_id", sa.String),
        sa.column("version", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("outcome", sa.String),
        sa.column("category", sa.String),
        sa.column("icon", sa.String),
        sa.column("required_integrations", sa.JSON),
        sa.column("optional_integrations", sa.JSON),
        sa.column("default_schedule_label", sa.String),
        sa.column("cost_tier", sa.String),
        sa.column("estimated_cost_usd", sa.JSON),
        sa.column("side_effect_policy", sa.String),
        sa.column("recommendation_reason_code", sa.String),
        sa.column("published_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
    )
    catalog = [
        {
            "key": "morning-command-center",
            "name": "Morning Command Center",
            "description": "Start the day with priorities, meetings, and important email.",
            "outcome": "A concise plan for the workday with sourced priorities and meetings to prepare.",
            "category": "daily_planning",
            "icon": "sunrise",
            "required": ["gmail", "google_calendar"],
            "optional": ["google_drive"],
            "schedule": "Weekdays at 07:30",
            "cost": "low",
            "max_cost": "0.08",
            "side_effect": "none",
            "reason": "CONNECTED_GMAIL_AND_CALENDAR",
        },
        {
            "key": "meeting-preparation",
            "name": "Meeting Preparation",
            "description": "Prepare a sourced briefing before customer and partner meetings.",
            "outcome": "A meeting briefing with attendees, company context, recent news, and open questions.",
            "category": "meetings",
            "icon": "calendar-clock",
            "required": ["google_calendar", "gmail"],
            "optional": ["google_drive"],
            "schedule": "Every hour",
            "cost": "medium",
            "max_cost": "0.20",
            "side_effect": "approval_required",
            "reason": "UPCOMING_MEETINGS",
        },
        {
            "key": "follow-up-radar",
            "name": "Follow-up Radar",
            "description": "Find customer conversations that need a response or next step.",
            "outcome": "A prioritized list of replies, commitments, and follow-ups that need attention.",
            "category": "follow_up",
            "icon": "inbox",
            "required": ["gmail"],
            "optional": ["google_calendar"],
            "schedule": "Every 2 hours on weekdays",
            "cost": "low",
            "max_cost": "0.10",
            "side_effect": "approval_required",
            "reason": "CUSTOMER_FOLLOW_UP_ACTIVITY",
        },
        {
            "key": "new-customer-intelligence",
            "name": "New Customer Intelligence",
            "description": "Research relevant customer and partner emails as they arrive.",
            "outcome": "A traceable company briefing and, when appropriate, a calendar proposal for review.",
            "category": "customer_intelligence",
            "icon": "search-check",
            "required": ["gmail"],
            "optional": ["google_calendar", "google_drive"],
            "schedule": "When a relevant email arrives",
            "cost": "medium",
            "max_cost": "0.25",
            "side_effect": "approval_required",
            "reason": None,
        },
        {
            "key": "end-of-day-client-digest",
            "name": "End-of-day Client Digest",
            "description": "Close the workday with customer activity, commitments, and tomorrow's focus.",
            "outcome": "A private digest of customer interactions, unfinished follow-ups, and tomorrow's meetings.",
            "category": "reporting",
            "icon": "sunset",
            "required": ["gmail", "google_calendar"],
            "optional": ["google_drive"],
            "schedule": "Weekdays at 17:30",
            "cost": "low",
            "max_cost": "0.10",
            "side_effect": "none",
            "reason": None,
        },
        {
            "key": "weekly-account-review",
            "name": "Weekly Account Review",
            "description": "Review the health of customer relationships at the end of the week.",
            "outcome": "A sourced account review with inactivity risks, commitments, opportunities, and next actions.",
            "category": "reporting",
            "icon": "chart-no-axes-combined",
            "required": ["gmail", "google_calendar"],
            "optional": ["google_drive"],
            "schedule": "Fridays at 16:00",
            "cost": "medium",
            "max_cost": "0.35",
            "side_effect": "approval_required",
            "reason": None,
        },
    ]
    template_rows = []
    version_rows = []
    for index, item in enumerate(catalog, start=1):
        template_id = f"workflow-template-{index:02d}"
        template_rows.append(
            {"id": template_id, "key": item["key"], "status": "published", "created_at": now, "updated_at": now}
        )
        version_rows.append(
            {
                "id": f"workflow-template-version-{index:02d}",
                "template_id": template_id,
                "version": 1,
                "name": item["name"],
                "description": item["description"],
                "outcome": item["outcome"],
                "category": item["category"],
                "icon": item["icon"],
                "required_integrations": item["required"],
                "optional_integrations": item["optional"],
                "default_schedule_label": item["schedule"],
                "cost_tier": item["cost"],
                "estimated_cost_usd": {"per_run_max": item["max_cost"]},
                "side_effect_policy": item["side_effect"],
                "recommendation_reason_code": item["reason"],
                "published_at": now,
                "created_at": now,
            }
        )
    op.bulk_insert(templates, template_rows)
    op.bulk_insert(versions, version_rows)


def downgrade() -> None:
    op.drop_index("ix_workflow_template_versions_category", table_name="workflow_template_versions")
    op.drop_index("ix_workflow_template_versions_template_id", table_name="workflow_template_versions")
    op.drop_table("workflow_template_versions")
    op.drop_index("ix_workflow_templates_key", table_name="workflow_templates")
    op.drop_table("workflow_templates")
