"""Scope workflow name uniqueness to (org_id, created_by_user_id, name)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0058_scope_workflow_name_unique_to_user"
down_revision: str | None = "0057_cleanup_unowned_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "postgresql":
        # Drop old org-wide unique constraint if exists
        op.execute("ALTER TABLE workflows DROP CONSTRAINT IF EXISTS uq_workflows_org_name")
        # Create user-scoped unique constraint/index
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflows_org_user_name "
            "ON workflows (org_id, created_by_user_id, name)"
        )
    else:
        # SQLite
        with op.batch_alter_table("workflows") as batch_op:
            batch_op.drop_constraint("uq_workflows_org_name", type_="unique")
            batch_op.create_unique_constraint("uq_workflows_org_user_name", ["org_id", "created_by_user_id", "name"])


def downgrade() -> None:
    pass
