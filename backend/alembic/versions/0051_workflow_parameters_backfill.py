"""Backfill workflow graph node `config` → `parameters` and index run listing.

Existing workflows store node configuration under the legacy ``config`` key.
The upgraded engine reads ``parameters`` first (falling back to ``config``),
but the UI and validation now treat ``parameters`` as canonical, so we migrate
every stored graph's nodes to expose ``parameters``.

Also adds an index on ``workflow_runs(workflow_id, status, started_at)`` to
support the run-history listing endpoint.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051_workflow_parameters_backfill"
down_revision: str | None = "0050_automation_template_dag_graphs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name
    workflow_columns = {column["name"] for column in sa.inspect(conn).get_columns("workflows")}

    # Older databases called this JSON column ``definition``.  Add the
    # canonical column before the backfill so upgrades from those schemas do
    # not fail while reading ``workflows.graph``.
    if "graph" not in workflow_columns:
        op.add_column("workflows", sa.Column("graph", sa.JSON(), nullable=True))
        if "definition" in workflow_columns:
            conn.execute(sa.text("UPDATE workflows SET graph = definition WHERE graph IS NULL"))

    if dialect == "postgresql":
        # JSONB surgery: for each node with config and no parameters, copy.
        conn.execute(
            sa.text(
                """
                UPDATE workflows
                SET graph = jsonb_set(
                        graph,
                        ARRAY['nodes'],
                        (
                            SELECT jsonb_agg(
                                CASE
                                    WHEN (n.value->>'parameters') IS NULL
                                     AND n.value->'config' IS NOT NULL
                                    THEN jsonb_set(n.value, '{parameters}', n.value->'config')
                                    ELSE n.value
                                END
                            )
                            FROM jsonb_array_elements(graph->'nodes') AS n(value)
                        ),
                        false
                    )
                WHERE graph->'nodes' IS NOT NULL
                """
            )
        )
    else:
        # SQLite: iterate rows in Python and rewrite the graph JSON.
        rows = conn.execute(sa.text("SELECT id, graph FROM workflows WHERE graph IS NOT NULL")).fetchall()
        for workflow_id, graph_raw in rows:
            if not graph_raw:
                continue
            graph = graph_raw if isinstance(graph_raw, dict) else _safe_loads(graph_raw)
            if not isinstance(graph, dict):
                continue
            nodes = graph.get("nodes")
            if not isinstance(nodes, list):
                continue
            changed = False
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("parameters") is None and node.get("config") is not None:
                    node["parameters"] = dict(node["config"])
                    changed = True
            if changed:
                import json

                conn.execute(
                    sa.text("UPDATE workflows SET graph = :graph WHERE id = :id"),
                    {"graph": json.dumps(graph), "id": workflow_id},
                )

    # Index for run-history listing (workflow_id, status, started_at)
    op.create_index(
        "ix_workflow_runs_wf_status_started",
        "workflow_runs",
        ["workflow_id", "status", "started_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_wf_status_started", table_name="workflow_runs", if_exists=True)


def _safe_loads(raw: str) -> dict | None:
    import json

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
