"""Add session-level tool execution policy."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0063_session_exec_policy"
down_revision: str | None = "0062_merge_tool_workflow_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "execution_policy",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "execution_policy")
