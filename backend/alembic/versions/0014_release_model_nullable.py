"""agent_releases.model_id nullable, ON DELETE SET NULL

Revision ID: 0014_agent_release_model_id_nullable
Revises: 0013_agent_model_id_nullable
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014_release_model_nullable"
down_revision: str | None = "0013_agent_model_id_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_releases") as batch_op:
        batch_op.alter_column("model_id", existing_type=sa.String(36), nullable=True)
        batch_op.drop_constraint("agent_releases_model_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "agent_releases_model_id_fkey", "models", ["model_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_releases") as batch_op:
        batch_op.drop_constraint("agent_releases_model_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("agent_releases_model_id_fkey", "models", ["model_id"], ["id"])
        batch_op.alter_column("model_id", existing_type=sa.String(36), nullable=False)
