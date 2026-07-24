"""add organization quotas

Revision ID: 0012_add_organization_quotas
Revises: 0011_add_evaluation_framework
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_add_organization_quotas"
down_revision: str | None = "0011_add_evaluation_framework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_quotas",
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("agent_runs_per_minute", sa.Integer(), nullable=False),
        sa.Column("max_concurrent_runs", sa.Integer(), nullable=False),
        sa.Column("monthly_cost_usd", sa.Float(), nullable=False),
        sa.Column("max_agents", sa.Integer(), nullable=True),
        sa.Column("max_workflows", sa.Integer(), nullable=True),
        sa.Column("max_storage_bytes", sa.Integer(), nullable=True),
        sa.Column("enforcement_mode", sa.String(length=16), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "enforcement_mode IN ('enforce', 'observe')",
            name="ck_organization_quotas_enforcement_mode",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("org_id"),
    )
    op.execute(
        """
        INSERT INTO organization_quotas (
            org_id, requests_per_minute, agent_runs_per_minute,
            max_concurrent_runs, monthly_cost_usd, enforcement_mode,
            created_at, updated_at
        )
        SELECT id, 600, 60, 10, 100.0, 'enforce',
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM organizations
        """
    )


def downgrade() -> None:
    op.drop_table("organization_quotas")
