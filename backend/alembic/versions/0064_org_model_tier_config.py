"""Create org_model_tier_config table for org-wide tier-based model routing.

Revision ID: 0064_org_model_tier_config
Revises: 0063_session_exec_policy
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0064_org_model_tier_config"
down_revision: str | None = "0063_session_exec_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_model_tier_config",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tier", sa.String(length=32), nullable=False, index=True),
        sa.Column(
            "model_id",
            sa.String(length=36),
            sa.ForeignKey("models.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("org_id", "tier", name="uq_org_model_tier_config"),
    )


def downgrade() -> None:
    op.drop_table("org_model_tier_config")
