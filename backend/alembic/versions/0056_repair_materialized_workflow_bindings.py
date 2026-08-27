"""Bind legacy materialized graphs to their installation runtime settings."""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.workflow.template_dags import materialize_template_graph

revision: str = "0056_repair_materialized_workflow_bindings"
down_revision: str | None = "0055_materialize_legacy_workflow_graphs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NAME_TO_TEMPLATE = {
    "Weekly Account Review": "weekly-account-review",
    "End-of-day Client Digest": "end-of-day-client-digest",
    "Meeting Preparation": "meeting-preparation",
    "Follow-up Radar": "follow-up-radar",
    "Morning Command Center": "morning-command-center",
    "Monitor and triage new Gmail": "gmail_monitor_and_triage",
    "New Customer Intelligence": "new-customer-intelligence",
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT w.id, w.org_id, w.name, w.graph,
                   i.timezone, i.schedule, i.settings
            FROM workflows w
            JOIN workflow_installations i ON i.workflow_id = w.id
            WHERE i.status <> 'archived'
            """
        )
    ).fetchall()
    agents: dict[str, str] = {}
    for row in conn.execute(
        sa.text(
            "SELECT org_id, id FROM agents "
            "WHERE model_id IS NOT NULL ORDER BY created_at"
        )
    ).mappings():
        agents.setdefault(row["org_id"], row["id"])
    models: dict[str, str] = {}
    for row in conn.execute(
        sa.text(
            "SELECT org_id, id FROM models "
            "WHERE enabled = true AND active = true ORDER BY created_at"
        )
    ).mappings():
        models.setdefault(row["org_id"], row["id"])

    repaired = 0
    for row in rows:
        template_key = _NAME_TO_TEMPLATE.get(row.name)
        graph = _loads(row.graph)
        if template_key is None or not isinstance(graph, dict):
            continue
        if graph.get("graph_runtime_version") == 1:
            continue
        settings = _loads(row.settings) or {}
        schedule = _loads(row.schedule) or {}
        bound = materialize_template_graph(
            template_key,
            timezone=row.timezone,
            schedule=schedule,
            settings=settings,
            default_agent_id=agents.get(row.org_id),
            default_model_id=models.get(row.org_id),
        )
        bound["graph_runtime_version"] = 1
        payload = json.dumps(bound, separators=(",", ":"))
        if conn.dialect.name == "postgresql":
            conn.execute(
                sa.text("UPDATE workflows SET graph = CAST(:graph AS json) WHERE id = :id"),
                {"graph": payload, "id": row.id},
            )
        else:
            conn.execute(
                sa.text("UPDATE workflows SET graph = :graph WHERE id = :id"),
                {"graph": payload, "id": row.id},
            )
        repaired += 1
    if repaired:
        print(f"repaired {repaired} materialized workflow graph bindings")


def downgrade() -> None:
    # Binding runtime settings is intentionally not undone: doing so would
    # make existing workflows fail again after a downgrade.
    pass


def _loads(raw: object) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
