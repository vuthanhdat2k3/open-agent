from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workflow.templates import SYSTEM_WORKFLOW_BLUEPRINTS
from app.db.base import gen_id, utc_now
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion

logger = structlog.get_logger(__name__)

# Metadata mapping for built-in catalog templates
SYSTEM_CATALOG_METADATA: dict[str, dict[str, Any]] = {
    "morning-command-center": {
        "outcome": "A concise plan for the workday with sourced priorities and meetings to prepare.",
        "required_integrations": ["gmail", "google_calendar"],
        "optional_integrations": ["google_drive"],
        "default_schedule_label": "Weekdays at 07:30",
        "cost_tier": "low",
        "estimated_cost_usd": {"per_run_max": "0.08"},
        "side_effect_policy": "none",
        "recommendation_reason_code": "CONNECTED_GMAIL_AND_CALENDAR",
    },
    "meeting-preparation": {
        "outcome": "A meeting briefing with attendees, company context, recent news, and open questions.",
        "required_integrations": ["google_calendar", "gmail"],
        "optional_integrations": ["google_drive"],
        "default_schedule_label": "Every hour",
        "cost_tier": "medium",
        "estimated_cost_usd": {"per_run_max": "0.20"},
        "side_effect_policy": "approval_required",
        "recommendation_reason_code": "UPCOMING_MEETINGS",
    },
    "follow-up-radar": {
        "outcome": "A prioritized list of replies, commitments, and follow-ups that need attention.",
        "required_integrations": ["gmail"],
        "optional_integrations": ["google_calendar"],
        "default_schedule_label": "Every 2 hours on weekdays",
        "cost_tier": "low",
        "estimated_cost_usd": {"per_run_max": "0.10"},
        "side_effect_policy": "approval_required",
        "recommendation_reason_code": "CUSTOMER_FOLLOW_UP_ACTIVITY",
    },
    "new-customer-intelligence": {
        "outcome": "A traceable company briefing and, when appropriate, a calendar proposal for review.",
        "required_integrations": ["gmail"],
        "optional_integrations": ["google_calendar", "google_drive"],
        "default_schedule_label": "When a relevant email arrives",
        "cost_tier": "medium",
        "estimated_cost_usd": {"per_run_max": "0.25"},
        "side_effect_policy": "approval_required",
        "recommendation_reason_code": None,
    },
    "end-of-day-client-digest": {
        "outcome": "A private digest of customer interactions, unfinished follow-ups, and tomorrow's meetings.",
        "required_integrations": ["gmail", "google_calendar"],
        "optional_integrations": ["google_drive"],
        "default_schedule_label": "Weekdays at 17:30",
        "cost_tier": "low",
        "estimated_cost_usd": {"per_run_max": "0.10"},
        "side_effect_policy": "none",
        "recommendation_reason_code": None,
    },
    "weekly-account-review": {
        "outcome": "A sourced account review with inactivity risks, commitments, opportunities, and next actions.",
        "required_integrations": ["gmail", "google_calendar"],
        "optional_integrations": ["google_drive"],
        "default_schedule_label": "Fridays at 16:00",
        "cost_tier": "medium",
        "estimated_cost_usd": {"per_run_max": "0.35"},
        "side_effect_policy": "approval_required",
        "recommendation_reason_code": None,
    },
    "gmail_monitor_and_triage": {
        "outcome": "Every new email is safely classified and routed without rescanning the mailbox on restart.",
        "required_integrations": ["gmail"],
        "optional_integrations": ["google_calendar"],
        "default_schedule_label": "When a new email arrives",
        "cost_tier": "low",
        "estimated_cost_usd": {"per_run_max": "0.05"},
        "side_effect_policy": "approval_required",
        "recommendation_reason_code": "CONNECTED_GMAIL",
    },
}


async def sync_system_workflow_templates(db: AsyncSession) -> None:
    """Ensure all built-in system workflow blueprints are registered in WorkflowCatalog."""
    now = utc_now()
    for bp_key, blueprint in SYSTEM_WORKFLOW_BLUEPRINTS.items():
        meta = SYSTEM_CATALOG_METADATA.get(bp_key, {})
        template = await db.scalar(
            select(WorkflowTemplate).where(WorkflowTemplate.key == bp_key)
        )
        if template is None:
            template = WorkflowTemplate(
                id=f"workflow-template-{bp_key[:18]}",
                org_id=None,
                created_by_user_id=None,
                key=bp_key,
                status="published",
                created_at=now,
                updated_at=now,
            )
            db.add(template)
            await db.flush()

        # Ensure latest published version exists
        version_row = await db.scalar(
            select(WorkflowTemplateVersion)
            .where(WorkflowTemplateVersion.template_id == template.id)
            .order_by(WorkflowTemplateVersion.version.desc())
            .limit(1)
        )
        if version_row is None:
            version = WorkflowTemplateVersion(
                id=gen_id(),
                template_id=template.id,
                version=1,
                name=blueprint.name,
                description=blueprint.description,
                outcome=meta.get("outcome", "Automated system workflow."),
                category=blueprint.category,
                icon=blueprint.icon,
                required_integrations=meta.get("required_integrations", []),
                optional_integrations=meta.get("optional_integrations", []),
                default_schedule_label=meta.get("default_schedule_label", "On demand"),
                cost_tier=meta.get("cost_tier", "low"),
                estimated_cost_usd=meta.get("estimated_cost_usd", {}),
                side_effect_policy=meta.get("side_effect_policy", "approval_required"),
                recommendation_reason_code=meta.get("recommendation_reason_code"),
                published_at=now,
                created_at=now,
            )
            db.add(version)
        else:
            # Sync metadata updates if needed
            version_row.name = blueprint.name
            version_row.description = blueprint.description
            version_row.category = blueprint.category
            version_row.icon = blueprint.icon
            if not version_row.published_at:
                version_row.published_at = now

    await db.commit()
    logger.info("system_workflow_templates_synced", count=len(SYSTEM_WORKFLOW_BLUEPRINTS))
