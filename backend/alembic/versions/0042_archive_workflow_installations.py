"""Preserve workflow history when a catalog installation is archived."""

import sqlalchemy as sa

from alembic import op

revision = "0042_archive_workflow_installations"
down_revision = "0041_gmail_monitor_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_installations") as batch:
        batch.drop_constraint("uq_workflow_installation_owner_template", type_="unique")
    op.create_index(
        "uq_active_workflow_installation_owner_template",
        "workflow_installations",
        ["org_id", "owner_user_id", "template_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'archived'"),
        sqlite_where=sa.text("status <> 'archived'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_workflow_installation_owner_template", table_name="workflow_installations")
    with op.batch_alter_table("workflow_installations") as batch:
        batch.create_unique_constraint(
            "uq_workflow_installation_owner_template",
            ["org_id", "owner_user_id", "template_key"],
        )
