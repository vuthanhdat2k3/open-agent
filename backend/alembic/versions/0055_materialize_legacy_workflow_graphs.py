"""Materialize legacy catalog workflows as editable graph definitions."""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.workflow.template_dags import TEMPLATE_DAGS

revision: str = "0055_materialize_legacy_workflow_graphs"
down_revision: str | None = "0054_graph_first_workflow_runtime"
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
    dialect = conn.dialect.name
    rows = conn.execute(sa.text("SELECT id, name, graph FROM workflows")).fetchall()
    migrated = 0
    for workflow_id, name, graph_raw in rows:
        template_key = _NAME_TO_TEMPLATE.get(name)
        if template_key is None or template_key not in TEMPLATE_DAGS:
            continue
        graph = graph_raw if isinstance(graph_raw, dict) else _loads(graph_raw)
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list) and graph["nodes"]:
            continue
        graph_json = json.dumps(TEMPLATE_DAGS[template_key], separators=(",", ":"))
        if dialect == "postgresql":
            conn.execute(
                sa.text("UPDATE workflows SET graph = CAST(:graph AS json) WHERE id = :id"),
                {"graph": graph_json, "id": workflow_id},
            )
        else:
            conn.execute(
                sa.text("UPDATE workflows SET graph = :graph WHERE id = :id"),
                {"graph": graph_json, "id": workflow_id},
            )
        migrated += 1
    if migrated:
        print(f"materialized {migrated} legacy workflow graphs")


def downgrade() -> None:
    # Deliberately retain materialized graphs. Removing them would destroy
    # user-editable workflow definitions and cannot be safely reversed.
    pass


def _loads(raw: object) -> dict | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
