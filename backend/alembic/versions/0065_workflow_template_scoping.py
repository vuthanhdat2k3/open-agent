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
    op.add_column(
        "workflow_templates",
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "workflow_templates",
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_workflow_templates_org_id", "workflow_templates", ["org_id"])
    op.create_index(
        "ix_workflow_templates_created_by_user_id", "workflow_templates", ["created_by_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_templates_created_by_user_id", table_name="workflow_templates")
    op.drop_index("ix_workflow_templates_org_id", table_name="workflow_templates")
    op.drop_column("workflow_templates", "created_by_user_id")
    op.drop_column("workflow_templates", "org_id")
