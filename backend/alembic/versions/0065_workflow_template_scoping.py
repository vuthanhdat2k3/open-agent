"""Add org_id and created_by_user_id to workflow_templates for marketplace scoping and ownership.

Revision ID: 0065_workflow_template_scoping
Revises: 0064_org_model_tier_config
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0065_workflow_template_scoping"
down_revision: str | None = "0064_org_model_tier_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_templates") as batch_op:
        batch_op.add_column(
            sa.Column(
                "org_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "organizations.id", ondelete="CASCADE", name="fk_workflow_templates_org_id"
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "created_by_user_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "users.id", ondelete="SET NULL", name="fk_workflow_templates_created_by_user_id"
                ),
                nullable=True,
            )
        )
        batch_op.create_index("ix_workflow_templates_org_id", ["org_id"])
        batch_op.create_index("ix_workflow_templates_created_by_user_id", ["created_by_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("workflow_templates") as batch_op:
        batch_op.drop_index("ix_workflow_templates_created_by_user_id")
        batch_op.drop_index("ix_workflow_templates_org_id")
        batch_op.drop_column("created_by_user_id")
        batch_op.drop_column("org_id")
