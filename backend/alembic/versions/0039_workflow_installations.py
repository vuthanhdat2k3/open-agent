"""Add user-owned workflow installations for the guided catalog setup."""

import sqlalchemy as sa

from alembic import op

revision = "0039_workflow_installations"
down_revision = "0038_workflow_template_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_installations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("template_key", sa.String(length=96), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id"),
        sa.UniqueConstraint("org_id", "owner_user_id", "template_key", name="uq_workflow_installation_owner_template"),
    )
    op.create_index("ix_workflow_installations_org_id", "workflow_installations", ["org_id"], unique=False)
    op.create_index("ix_workflow_installations_owner_user_id", "workflow_installations", ["owner_user_id"], unique=False)
    op.create_index("ix_workflow_installations_template_key", "workflow_installations", ["template_key"], unique=False)
    op.create_index("ix_workflow_installations_status", "workflow_installations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workflow_installations_status", table_name="workflow_installations")
    op.drop_index("ix_workflow_installations_template_key", table_name="workflow_installations")
    op.drop_index("ix_workflow_installations_owner_user_id", table_name="workflow_installations")
    op.drop_index("ix_workflow_installations_org_id", table_name="workflow_installations")
    op.drop_table("workflow_installations")
