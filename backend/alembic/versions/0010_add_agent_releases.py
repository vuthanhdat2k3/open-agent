"""add immutable agent releases

Revision ID: 0010_add_agent_releases
Revises: 0009_add_audit_logs
Create Date: 2026-07-24
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0010_add_agent_releases"
down_revision: str | None = "0009_add_audit_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONFIG_FIELDS = (
    "description",
    "system_prompt",
    "model_id",
    "tools",
    "allowed_risk_tiers",
    "kind",
    "max_iterations",
    "temperature",
)


def _config_hash(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "agent_releases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("allowed_risk_tiers", sa.JSON(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("change_note", sa.String(length=512), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("published_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version", name="uq_agent_releases_agent_version"),
    )
    op.create_index("ix_agent_releases_agent_id", "agent_releases", ["agent_id"])
    op.create_index("ix_agent_releases_config_hash", "agent_releases", ["config_hash"])
    op.create_index("ix_agent_releases_org_id", "agent_releases", ["org_id"])
    op.create_index("ix_agent_releases_status", "agent_releases", ["status"])

    with op.batch_alter_table("agents") as batch_op:
        batch_op.add_column(sa.Column("active_release_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "latest_release_number",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_foreign_key(
            "fk_agents_active_release_id",
            "agent_releases",
            ["active_release_id"],
            ["id"],
            ondelete="SET NULL",
        )

    for table_name in ("sessions", "tasks", "workflow_node_runs"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column("agent_release_id", sa.String(length=36), nullable=True)
            )
            batch_op.create_foreign_key(
                f"fk_{table_name}_agent_release_id",
                "agent_releases",
                ["agent_release_id"],
                ["id"],
                ondelete="SET NULL",
            )

    bind = op.get_bind()
    agents = sa.table(
        "agents",
        sa.column("id", sa.String()),
        sa.column("org_id", sa.String()),
        sa.column("created_by_user_id", sa.String()),
        sa.column("description", sa.String()),
        sa.column("system_prompt", sa.Text()),
        sa.column("model_id", sa.String()),
        sa.column("tools", sa.JSON()),
        sa.column("allowed_risk_tiers", sa.JSON()),
        sa.column("kind", sa.String()),
        sa.column("max_iterations", sa.Integer()),
        sa.column("temperature", sa.Float()),
    )
    releases = sa.table(
        "agent_releases",
        sa.column("id", sa.String()),
        sa.column("org_id", sa.String()),
        sa.column("agent_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("description", sa.String()),
        sa.column("system_prompt", sa.Text()),
        sa.column("model_id", sa.String()),
        sa.column("tools", sa.JSON()),
        sa.column("allowed_risk_tiers", sa.JSON()),
        sa.column("kind", sa.String()),
        sa.column("max_iterations", sa.Integer()),
        sa.column("temperature", sa.Float()),
        sa.column("change_note", sa.String()),
        sa.column("config_hash", sa.String()),
        sa.column("created_by_user_id", sa.String()),
        sa.column("published_by_user_id", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("published_at", sa.DateTime()),
    )
    agent_rows = bind.execute(sa.select(agents)).mappings().all()
    now = datetime.utcnow()
    for row in agent_rows:
        release_id = str(uuid.uuid4())
        config = {field: row[field] for field in CONFIG_FIELDS}
        bind.execute(
            releases.insert().values(
                id=release_id,
                org_id=row["org_id"],
                agent_id=row["id"],
                version=1,
                status="published",
                **config,
                change_note="Backfilled initial release",
                config_hash=_config_hash(config),
                created_by_user_id=row["created_by_user_id"],
                published_by_user_id=row["created_by_user_id"],
                created_at=now,
                published_at=now,
            )
        )
        bind.execute(
            sa.text(
                "UPDATE agents SET active_release_id = :release_id, "
                "latest_release_number = 1 WHERE id = :agent_id"
            ),
            {"release_id": release_id, "agent_id": row["id"]},
        )


def downgrade() -> None:
    for table_name in ("workflow_node_runs", "tasks", "sessions"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(
                f"fk_{table_name}_agent_release_id", type_="foreignkey"
            )
            batch_op.drop_column("agent_release_id")

    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_constraint("fk_agents_active_release_id", type_="foreignkey")
        batch_op.drop_column("latest_release_number")
        batch_op.drop_column("active_release_id")

    op.drop_index("ix_agent_releases_status", table_name="agent_releases")
    op.drop_index("ix_agent_releases_org_id", table_name="agent_releases")
    op.drop_index("ix_agent_releases_config_hash", table_name="agent_releases")
    op.drop_index("ix_agent_releases_agent_id", table_name="agent_releases")
    op.drop_table("agent_releases")
