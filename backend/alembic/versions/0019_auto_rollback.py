"""auto-rollback configuration on agents

Revision ID: 0019_auto_rollback
Revises: 0018_closed_eval_loop
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0019_auto_rollback"
down_revision: str | None = "0018_closed_eval_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "auto_rollback_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("agents", sa.Column("auto_rollback_min_pass_rate", sa.Float(), nullable=True))
    op.add_column(
        "agents",
        sa.Column(
            "auto_rollback_cooldown_minutes", sa.Integer(), nullable=False, server_default="60"
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "auto_rollback_cooldown_minutes")
    op.drop_column("agents", "auto_rollback_min_pass_rate")
    op.drop_column("agents", "auto_rollback_enabled")
