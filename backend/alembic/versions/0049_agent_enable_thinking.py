"""Add per-agent enable_thinking control (null = model default)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0049_agent_enable_thinking"
down_revision: str | None = "0048_platform_admin_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("enable_thinking", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "enable_thinking")
