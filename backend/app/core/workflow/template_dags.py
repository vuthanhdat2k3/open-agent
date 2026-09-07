from __future__ import annotations

import copy
from typing import Any

TEMPLATE_DAGS = {
    "morning-command-center": {
        "kind": "catalog_template",
        "template_key": "morning-command-center",
        "template_version": 1,
        "nodes": [
            {
                "id": "scheduler",
                "kind": "scheduler",
                "label": "Weekdays 07:30 Trigger",
                "parameters": {"frequency": "custom", "custom_cron": "0 7 * * 1-5"},
            },
            {
                "id": "integration",
                "kind": "integration",
                "label": "Fetch Gmail & Calendar",
                "parameters": {"source": "gmail_and_calendar", "operation": "list_new", "max_results": 20},
            },
            {
                "id": "triager",
                "kind": "triager",
                "label": "Prioritize Tasks & Meetings",
                "parameters": {"mode": "llm", "categories": "high_priority, meetings, reminders"},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "Executive Briefing Synthesizer",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {
                "id": "output",
                "kind": "output",
                "label": "Morning Command Center Digest",
                "parameters": {"include": "all_inputs"},
            },
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
            {
                "id": "scheduler",
                "kind": "scheduler",
                "label": "Hourly Meeting Scanner",
                "parameters": {"frequency": "hourly"},
            },
            {
                "id": "integration",
                "kind": "integration",
                "label": "Calendar & Drive Scanner",
                "parameters": {"source": "google_calendar", "operation": "list_events", "max_results": 20},
            },
            {
                "id": "triager",
                "kind": "triager",
                "label": "Filter Upcoming Client Meetings",
                "parameters": {"mode": "llm", "categories": "client_meeting, internal"},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "Meeting Context & Dossier Agent",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {"id": "output", "kind": "output", "label": "Executive Meeting Dossier", "parameters": {"include": "all_inputs"}},
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
            {
                "id": "scheduler",
                "kind": "scheduler",
                "label": "Daily Follow-up Radar",
                "parameters": {"frequency": "custom", "custom_cron": "0 9 * * 1-5"},
            },
            {
                "id": "integration",
                "kind": "integration",
                "label": "Gmail Sent & Threads Inspector",
                "parameters": {"source": "gmail", "operation": "list_new", "max_results": 20},
            },
            {
                "id": "triager",
                "kind": "triager",
                "label": "Identify Unanswered Threads (>3d)",
                "parameters": {"mode": "llm", "categories": "follow_up, done"},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "Follow-up Strategy & Draft Composer",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {
                "id": "approval",
                "kind": "approval",
                "label": "Review & Approve Follow-up Draft",
                "parameters": {"title": "Approve this workflow step"},
            },
            {
                "id": "output",
                "kind": "output",
                "label": "Dispatched Follow-up Action",
                "parameters": {"include": "all_inputs"},
            },
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
            {
                "id": "input",
                "kind": "input",
                "label": "Inbound Email Event",
                "parameters": {"input_field": "Inbound Email Event"},
            },
            {
                "id": "integration",
                "kind": "integration",
                "label": "Extract Sender & Domain Info",
                "parameters": {"source": "gmail", "operation": "list_new", "max_results": 20},
            },
            {
                "id": "triager",
                "kind": "triager",
                "label": "Qualify ICP & Domain",
                "parameters": {"mode": "llm", "categories": "enterprise, smb, personal"},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "Company Research & Profiler Agent",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {
                "id": "output",
                "kind": "output",
                "label": "Enriched Customer Intelligence Dossier",
                "parameters": {"include": "all_inputs"},
            },
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
            {
                "id": "scheduler",
                "kind": "scheduler",
                "label": "Daily 17:30 EOD Trigger",
                "parameters": {"frequency": "custom", "custom_cron": "30 17 * * 1-5"},
            },
            {
                "id": "integration",
                "kind": "integration",
                "label": "Collect Today's Email & Actions",
                "parameters": {"source": "gmail", "operation": "list_new", "max_results": 20},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "EOD Summary & Highlights Compiler",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {
                "id": "output",
                "kind": "output",
                "label": "Executive EOD Client Digest",
                "parameters": {"include": "all_inputs"},
            },
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
            {
                "id": "scheduler",
                "kind": "scheduler",
                "label": "Monday 08:00 Weekly Trigger",
                "parameters": {"frequency": "weekly", "time": "08:00", "days_of_week": ["mon"]},
            },
            {
                "id": "integration",
                "kind": "integration",
                "label": "Aggregate Weekly Activity & Cases",
                "parameters": {"source": "gmail_and_calendar", "operation": "list_new", "max_results": 20},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "Account Health & Risk Analysis Agent",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {
                "id": "output",
                "kind": "output",
                "label": "Weekly Account Health Scorecard",
                "parameters": {"include": "all_inputs"},
            },
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
            {
                "id": "input",
                "kind": "input",
                "label": "New Gmail Inbound Message",
                "parameters": {"input_field": "New Gmail Inbound Message"},
            },
            {
                "id": "triager",
                "kind": "triager",
                "label": "Smart Intent & Urgency Classifier",
                "parameters": {"mode": "llm", "categories": "urgent, sales, support, newsletter"},
            },
            {
                "id": "agent",
                "kind": "agent",
                "label": "Automated Draft & Triage Handler",
                "parameters": {"mode": "custom", "system_prompt": "You are a helpful workflow agent."},
            },
            {
                "id": "approval",
                "kind": "approval",
                "label": "Human Approval for High-Impact Actions",
                "parameters": {"title": "Approve this workflow step"},
            },
            {
                "id": "output",
                "kind": "output",
                "label": "Routed & Triaged Action Result",
                "parameters": {"include": "all_inputs"},
            },
        ],
        "edges": [
            {"from_": "input", "to": "triager"},
            {"from_": "triager", "to": "agent"},
            {"from_": "agent", "to": "approval"},
            {"from_": "approval", "to": "output"},
        ],
    },
}


_WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def materialize_template_graph(
    template_key: str,
    *,
    timezone: str | None = None,
    schedule: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    default_agent_id: str | None = None,
    default_model_id: str | None = None,
) -> dict[str, Any]:
    """Create an editable graph with installation settings bound to its nodes.

    Catalog templates are deliberately provider-agnostic. Once installed, the
    user's schedule, connections, and default agent must become part of the
    graph so the graph is the runtime source of truth.
    """
    template = TEMPLATE_DAGS.get(template_key)
    if template is None:
        raise KeyError(f"unknown workflow template: {template_key}")
    graph = copy.deepcopy(template)
    settings = dict(settings or {})
    schedule = dict(schedule or {})
    schedule_kind = str(schedule.get("kind") or "daily")

    for node in graph.get("nodes", []):
        parameters = dict(node.get("parameters") or {})
        kind = node.get("kind")

        if kind == "scheduler":
            if schedule_kind == "hourly":
                parameters.update({"frequency": "hourly", "timezone": timezone or "UTC"})
            elif schedule_kind in {"daily", "weekdays", "weekly"}:
                frequency = schedule_kind
                parameters.update(
                    {
                        "frequency": frequency,
                        "time": schedule.get("time") or parameters.get("time") or "07:30",
                        "timezone": timezone or "UTC",
                    }
                )
                if frequency == "weekly":
                    weekday = schedule.get("weekday")
                    if isinstance(weekday, int) and 0 <= weekday <= 6:
                        parameters["days_of_week"] = [_WEEKDAY_NAMES[weekday]]
                else:
                    parameters.pop("days_of_week", None)
            elif schedule_kind == "event":
                # Event templates should not retain a dormant scheduler node.
                continue
            parameters["enabled"] = True

        elif kind == "integration":
            source = str(parameters.get("source") or "").lower()
            if source == "gmail":
                if settings.get("connection_id"):
                    parameters["connection_id"] = settings["connection_id"]
            elif source == "google_calendar":
                connection_id = settings.get("calendar_connection_id") or settings.get("connection_id")
                if connection_id:
                    parameters["connection_id"] = connection_id
            elif source in {"gmail_and_calendar", "gmail_calendar"}:
                if settings.get("connection_id"):
                    parameters["connection_id"] = settings["connection_id"]
                if settings.get("calendar_connection_id"):
                    parameters["calendar_connection_id"] = settings["calendar_connection_id"]

        elif kind == "agent":
            agent_id = settings.get("agent_id") or node.get("agent_id") or default_agent_id
            model_id = settings.get("model_id") or parameters.get("model_id") or default_model_id
            if agent_id:
                node["agent_id"] = agent_id
                parameters["mode"] = "inherit"
                parameters["agent_id"] = agent_id
            elif model_id:
                parameters["mode"] = "custom"
                parameters["model_id"] = model_id
            else:
                # Runtime resolves this legacy-compatible node to the first
                # enabled org agent; do not invent an org-specific ID here.
                parameters.pop("mode", None)
                parameters.pop("system_prompt", None)

        if kind in {"input", "integration"} and schedule_kind == "event":
            parameters["trigger_type"] = "event"
            parameters["template_key"] = template_key

        node["parameters"] = parameters
        node["config"] = {}
    return graph
