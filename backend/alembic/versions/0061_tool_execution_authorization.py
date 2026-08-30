"""Persist tool classifications and workflow execution principals.

MCP discovery is untrusted: tools that were already discovered before this
migration are conservative until an operator explicitly reclassifies them.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# PostgreSQL's default alembic_version.version_num is VARCHAR(32). Keep this
# revision identifier within that limit (see 0045_identity_sessions /
# 0061_workflow_template_key_and_customized for the same constraint) - the
# original "0061_tool_execution_authorization" id (34 chars) was one byte
# over the wire and silently rolled back this migration's schema changes on
# every database that stamped it, since the INSERT into alembic_version
# failed inside the same transaction as the ADD COLUMN statements above.
revision: str = "0061_tool_exec_authz"
down_revision: str | None = "0060_profile_role_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("execution_principal", sa.JSON(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("execution_principal", sa.JSON(), nullable=True),
    )

    # ``mcp_tools`` has never been created by an Alembic migration - it only
    # ever comes into existence via ``Base.metadata.create_all()`` during the
    # app's initial bootstrap (see ``app.db.session.init_db``), which always
    # runs before any migration is ever applied to a given database. A
    # migration chain replayed against a database that predates the MCP
    # feature entirely (e.g. a pre-M1 fixture) legitimately has no such table
    # yet; skip it rather than fail the whole upgrade.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("mcp_tools"):
        op.add_column(
            "mcp_tools",
            sa.Column("risk_tier", sa.String(length=32), nullable=True),
        )
        op.add_column(
            "mcp_tools",
            sa.Column("requires_approval", sa.Boolean(), nullable=True),
        )
        # Fail closed for every previously discovered MCP tool. Operators may
        # later lower the risk only through an explicit management workflow.
        op.execute(sa.text("UPDATE mcp_tools SET risk_tier = 'dangerous' WHERE risk_tier IS NULL"))
        op.execute(
            sa.text("UPDATE mcp_tools SET requires_approval = TRUE WHERE requires_approval IS NULL")
        )
        with op.batch_alter_table("mcp_tools") as batch:
            batch.alter_column("risk_tier", existing_type=sa.String(length=32), nullable=False)
            batch.alter_column("requires_approval", existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("mcp_tools"):
        with op.batch_alter_table("mcp_tools") as batch:
            batch.drop_column("requires_approval")
            batch.drop_column("risk_tier")
    op.drop_column("tasks", "execution_principal")
    op.drop_column("workflow_runs", "execution_principal")
