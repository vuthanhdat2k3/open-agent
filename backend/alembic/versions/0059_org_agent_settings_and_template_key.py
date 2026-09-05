"""Add template_key and is_customized to agents, and create org_agent_settings table."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_org_agent_settings_and_template_key"
down_revision: str | None = "0058_scope_workflow_name_unique_to_user"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add columns to agents
    op.add_column("agents", sa.Column("template_key", sa.String(length=64), nullable=True))
    op.add_column(
        "agents",
        sa.Column("is_customized", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_agents_template_key", "agents", ["template_key"])

    # 2. Create org_agent_settings table
    op.create_table(
        "org_agent_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("template_key", sa.String(length=64), nullable=False, index=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "model_override_id",
            sa.String(length=36),
            sa.ForeignKey("models.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("temperature_override", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("org_id", "template_key", name="uq_org_agent_settings"),
    )


def downgrade() -> None:
    op.drop_table("org_agent_settings")
    op.drop_index("ix_agents_template_key", table_name="agents")
    op.drop_column("agents", "is_customized")
    op.drop_column("agents", "template_key")
