"""add allowed_risk_tiers to agents table

Revision ID: 0005_add_agent_allowed_risk_tiers
Revises: 0004_add_oauth_refresh_apikey
Create Date: 2026-07-23 00:00:03.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_agent_allowed_risk_tiers"
down_revision: str | None = "0004_add_oauth_refresh_apikey"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("agents"):
        cols = [c["name"] for c in inspector.get_columns("agents")]
        if "allowed_risk_tiers" not in cols:
            op.add_column("agents", sa.Column("allowed_risk_tiers", sa.JSON(), nullable=True))
            op.execute("UPDATE agents SET allowed_risk_tiers = '[\"safe\", \"read\"]' WHERE allowed_risk_tiers IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("agents"):
        cols = [c["name"] for c in inspector.get_columns("agents")]
        if "allowed_risk_tiers" in cols:
            op.drop_column("agents", "allowed_risk_tiers")
