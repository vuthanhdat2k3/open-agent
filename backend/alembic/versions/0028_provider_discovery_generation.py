"""Add provider discovery generation for durable async refresh."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_provider_discovery"
down_revision: str | None = "0027_approval_owning_task"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("discovery_generation", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("providers", "discovery_generation")
