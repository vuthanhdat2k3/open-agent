"""Add template_key and is_customized to workflows table."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# PostgreSQL's default alembic_version.version_num is VARCHAR(32). Keep
# this revision identifier within that limit so startup migrations can stamp
# the database after applying the schema change.
revision: str = "0061_workflow_template_custom"
down_revision: str | None = "0060_profile_role_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("template_key", sa.String(length=64), nullable=True))
    op.add_column(
        "workflows",
        sa.Column("is_customized", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_workflows_template_key", "workflows", ["template_key"])


def downgrade() -> None:
    op.drop_index("ix_workflows_template_key", table_name="workflows")
    op.drop_column("workflows", "is_customized")
    op.drop_column("workflows", "template_key")
