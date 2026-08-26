"""Populate DAG graphs for the 7 catalog automation workflow templates."""

from collections.abc import Sequence
import json
import sqlalchemy as sa
from alembic import op

revision: str = "0050_automation_template_dag_graphs"
down_revision: str | None = "0049_agent_enable_thinking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATE_DAGS = {
    "morning-command-center": {
        "kind": "catalog_template",
        "template_key": "morning-command-center",
        "template_version": 1,
        "nodes": [
            {"id": "scheduler", "kind": "scheduler", "label": "Weekdays 07:30 Trigger", "config": {"cron": "0 7 * * 1-5", "schedule_label": "Weekdays at 07:30"}},
            {"id": "integration", "kind": "integration", "label": "Fetch Gmail & Calendar", "config": {"source": "gmail_and_calendar"}},
            {"id": "triager", "kind": "triager", "label": "Prioritize Tasks & Meetings", "config": {"policy": "rank_by_urgency", "categories": "high_priority, meetings, reminders"}},
            {"id": "agent", "kind": "agent", "label": "Executive Briefing Synthesizer", "agent_id": None, "config": {}},
            {"id": "output", "kind": "output", "label": "Morning Command Center Digest", "config": {}},
        ],
        "edges": [
            {"from_": "scheduler", "to": "integration"},
            {"from_": "integration", "to": "triager"},
            {"from_": "triager", "to": "agent"},
            {"from_": "agent", "to": "output"},
        ],
    },
    "meeting-preparation": {
        "kind": "catalog_template",
        "template_key": "meeting-preparation",
        "template_version": 1,
        "nodes": [
            {"id": "scheduler", "kind": "scheduler", "label": "Hourly Meeting Scanner", "config": {"cron": "0 * * * *", "schedule_label": "Every hour"}},
            {"id": "integration", "kind": "integration", "label": "Calendar & Drive Scanner", "config": {"source": "google_calendar"}},
            {"id": "triager", "kind": "triager", "label": "Filter Upcoming Client Meetings", "config": {"policy": "filter_client_meetings", "window_hours": 24}},
            {"id": "agent", "kind": "agent", "label": "Meeting Context & Dossier Agent", "agent_id": None, "config": {}},
            {"id": "output", "kind": "output", "label": "Executive Meeting Dossier", "config": {}},
        ],
        "edges": [
            {"from_": "scheduler", "to": "integration"},
            {"from_": "integration", "to": "triager"},
            {"from_": "triager", "to": "agent"},
            {"from_": "agent", "to": "output"},
        ],
    },
    "follow-up-radar": {
        "kind": "catalog_template",
        "template_key": "follow-up-radar",
        "template_version": 1,
        "nodes": [
            {"id": "scheduler", "kind": "scheduler", "label": "Daily Follow-up Radar", "config": {"cron": "0 9 * * 1-5", "schedule_label": "Daily at 09:00"}},
            {"id": "integration", "kind": "integration", "label": "Gmail Sent & Threads Inspector", "config": {"source": "gmail"}},
            {"id": "triager", "kind": "triager", "label": "Identify Unanswered Threads (>3d)", "config": {"policy": "stale_conversations", "threshold_days": 3}},
            {"id": "agent", "kind": "agent", "label": "Follow-up Strategy & Draft Composer", "agent_id": None, "config": {}},
            {"id": "approval", "kind": "approval", "label": "Review & Approve Follow-up Draft", "config": {"tool_name": "send_email"}},
            {"id": "output", "kind": "output", "label": "Dispatched Follow-up Action", "config": {}},
        ],
        "edges": [
            {"from_": "scheduler", "to": "integration"},
            {"from_": "integration", "to": "triager"},
            {"from_": "triager", "to": "agent"},
            {"from_": "agent", "to": "approval"},
            {"from_": "approval", "to": "output"},
        ],
    },
    "new-customer-intelligence": {
        "kind": "catalog_template",
        "template_key": "new-customer-intelligence",
        "template_version": 1,
        "nodes": [
            {"id": "input", "kind": "input", "label": "Inbound Email Event", "config": {"event": "inbound_email"}},
            {"id": "integration", "kind": "integration", "label": "Extract Sender & Domain Info", "config": {"source": "gmail"}},
            {"id": "triager", "kind": "triager", "label": "Qualify ICP & Domain", "config": {"policy": "classify_lead", "categories": "enterprise, smb, personal"}},
            {"id": "agent", "kind": "agent", "label": "Company Research & Profiler Agent", "agent_id": None, "config": {}},
            {"id": "output", "kind": "output", "label": "Enriched Customer Intelligence Dossier", "config": {}},
        ],
        "edges": [
            {"from_": "input", "to": "integration"},
            {"from_": "integration", "to": "triager"},
            {"from_": "triager", "to": "agent"},
            {"from_": "agent", "to": "output"},
        ],
    },
    "end-of-day-client-digest": {
        "kind": "catalog_template",
        "template_key": "end-of-day-client-digest",
        "template_version": 1,
        "nodes": [
            {"id": "scheduler", "kind": "scheduler", "label": "Daily 17:30 EOD Trigger", "config": {"cron": "30 17 * * 1-5", "schedule_label": "Daily at 17:30"}},
            {"id": "integration", "kind": "integration", "label": "Collect Today's Email & Actions", "config": {"source": "gmail"}},
            {"id": "agent", "kind": "agent", "label": "EOD Summary & Highlights Compiler", "agent_id": None, "config": {}},
            {"id": "output", "kind": "output", "label": "Executive EOD Client Digest", "config": {}},
        ],
        "edges": [
            {"from_": "scheduler", "to": "integration"},
            {"from_": "integration", "to": "agent"},
            {"from_": "agent", "to": "output"},
        ],
    },
    "weekly-account-review": {
        "kind": "catalog_template",
        "template_key": "weekly-account-review",
        "template_version": 1,
        "nodes": [
            {"id": "scheduler", "kind": "scheduler", "label": "Monday 08:00 Weekly Trigger", "config": {"cron": "0 8 * * 1", "schedule_label": "Mondays at 08:00"}},
            {"id": "integration", "kind": "integration", "label": "Aggregate Weekly Activity & Cases", "config": {"source": "gmail_and_calendar"}},
            {"id": "agent", "kind": "agent", "label": "Account Health & Risk Analysis Agent", "agent_id": None, "config": {}},
            {"id": "output", "kind": "output", "label": "Weekly Account Health Scorecard", "config": {}},
        ],
        "edges": [
            {"from_": "scheduler", "to": "integration"},
            {"from_": "integration", "to": "agent"},
            {"from_": "agent", "to": "output"},
        ],
    },
    "gmail_monitor_and_triage": {
        "kind": "catalog_template",
        "template_key": "gmail_monitor_and_triage",
        "template_version": 1,
        "nodes": [
            {"id": "input", "kind": "input", "label": "New Gmail Inbound Message", "config": {"trigger": "gmail_webhook"}},
            {"id": "triager", "kind": "triager", "label": "Smart Intent & Urgency Classifier", "config": {"policy": "intent_classification", "categories": "urgent, sales, support, newsletter"}},
            {"id": "agent", "kind": "agent", "label": "Automated Draft & Triage Handler", "agent_id": None, "config": {}},
            {"id": "approval", "kind": "approval", "label": "Human Approval for High-Impact Actions", "config": {"tool_name": "send_email"}},
            {"id": "output", "kind": "output", "label": "Routed & Triaged Action Result", "config": {}},
        ],
        "edges": [
            {"from_": "input", "to": "triager"},
            {"from_": "triager", "to": "agent"},
            {"from_": "agent", "to": "approval"},
            {"from_": "approval", "to": "output"},
        ],
    },
}


def upgrade() -> None:
    conn = op.get_bind()
    for key, graph_dict in TEMPLATE_DAGS.items():
        # Update by template_key inside graph json, or by name matching
        graph_json = json.dumps(graph_dict)
        conn.execute(
            sa.text(
                "UPDATE workflows SET graph = :graph WHERE graph->>'template_key' = :key"
            ),
            {"graph": graph_json, "key": key},
        )


def downgrade() -> None:
    pass
