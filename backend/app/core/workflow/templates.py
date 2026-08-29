from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.workflow.template_dags import TEMPLATE_DAGS


@dataclass(frozen=True)
class SystemWorkflowBlueprint:
    key: str
    name: str
    description: str
    category: str
    icon: str
    graph: dict[str, Any]
    id: str


SYSTEM_WORKFLOW_BLUEPRINTS: dict[str, SystemWorkflowBlueprint] = {
    "morning-command-center": SystemWorkflowBlueprint(
        key="morning-command-center",
        name="Morning Command Center",
        description="Start the day with priorities, meetings, and important email.",
        category="daily_planning",
        icon="sunrise",
        graph=TEMPLATE_DAGS["morning-command-center"],
        id="sys-wf-morning-command-center",
    ),
    "meeting-preparation": SystemWorkflowBlueprint(
        key="meeting-preparation",
        name="Meeting Preparation",
        description="Prepare a sourced briefing before customer and partner meetings.",
        category="meetings",
        icon="calendar-clock",
        graph=TEMPLATE_DAGS["meeting-preparation"],
        id="sys-wf-meeting-preparation",
    ),
    "follow-up-radar": SystemWorkflowBlueprint(
        key="follow-up-radar",
        name="Follow-up Radar",
        description="Find customer conversations that need a response or next step.",
        category="follow_up",
        icon="inbox",
        graph=TEMPLATE_DAGS["follow-up-radar"],
        id="sys-wf-follow-up-radar",
    ),
    "new-customer-intelligence": SystemWorkflowBlueprint(
        key="new-customer-intelligence",
        name="New Customer Intelligence",
        description="Research relevant customer and partner emails as they arrive.",
        category="customer_intelligence",
        icon="search-check",
        graph=TEMPLATE_DAGS["new-customer-intelligence"],
        id="sys-wf-new-customer-intelligence",
    ),
    "end-of-day-client-digest": SystemWorkflowBlueprint(
        key="end-of-day-client-digest",
        name="End-of-day Client Digest",
        description="Close the workday with customer activity, commitments, and tomorrow's focus.",
        category="reporting",
        icon="sunset",
        graph=TEMPLATE_DAGS["end-of-day-client-digest"],
        id="sys-wf-end-of-day-client-digest",
    ),
    "weekly-account-review": SystemWorkflowBlueprint(
        key="weekly-account-review",
        name="Weekly Account Review",
        description="Review the health of customer relationships at the end of the week.",
        category="reporting",
        icon="chart-no-axes-combined",
        graph=TEMPLATE_DAGS["weekly-account-review"],
        id="sys-wf-weekly-account-review",
    ),
    "gmail_monitor_and_triage": SystemWorkflowBlueprint(
        key="gmail_monitor_and_triage",
        name="Gmail Monitor & Auto-Triage",
        description="Automatically monitor inbound emails, triage urgency, and draft responses.",
        category="customer_intelligence",
        icon="mail",
        graph=TEMPLATE_DAGS["gmail_monitor_and_triage"],
        id="sys-wf-gmail_monitor_and_triage",
    ),
}
