"""add org_id to business tables, backfill default org, enforce NOT NULL and FKs

Revision ID: 0003_add_org_id_and_backfill
Revises: 0002_add_org_user_membership
Create Date: 2026-07-23 00:00:01.000000
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_org_id_and_backfill"
down_revision: str | None = "0002_add_org_user_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUSINESS_TABLES = [
    "agents",
    "models",
    "providers",
    "mcp_servers",
    "workflows",
    "sessions",
    "messages",
    "usage_events",
    "uploaded_files",
    "agent_memories",
    "session_memories",
]

DEFAULT_ORG_ID = "default-org-id"
DEFAULT_USER_ID = "default-user-id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _has_column(table_name: str, col_name: str) -> bool:
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        return col_name in cols

    # 1. Add nullable org_id and created_by_user_id to business tables
    for table in BUSINESS_TABLES:
        if not _has_column(table, "org_id"):
            op.add_column(table, sa.Column("org_id", sa.String(length=36), nullable=True))
        if not _has_column(table, "created_by_user_id"):
            op.add_column(table, sa.Column("created_by_user_id", sa.String(length=36), nullable=True))

    # 2. Backfill: create default organization if not exists
    res = bind.execute(
        sa.text("SELECT id FROM organizations WHERE id = :id OR slug = 'default'"),
        {"id": DEFAULT_ORG_ID},
    ).first()

    org_id = DEFAULT_ORG_ID
    if not res:
        now_str = datetime.now(timezone.utc).isoformat()
        bind.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": DEFAULT_ORG_ID,
                "name": "Default Organization",
                "slug": "default",
                "created_at": now_str,
            },
        )
    else:
        org_id = res[0]

    # Create default user if not exists
    res_user = bind.execute(
        sa.text("SELECT id FROM users WHERE id = :id OR email = 'admin@openagent.local'"),
        {"id": DEFAULT_USER_ID},
    ).first()

    if not res_user:
        now_str = datetime.now(timezone.utc).isoformat()
        bind.execute(
            sa.text(
                "INSERT INTO users (id, email, display_name, is_active, created_at) "
                "VALUES (:id, :email, :display_name, 1, :created_at)"
            ),
            {
                "id": DEFAULT_USER_ID,
                "email": "admin@openagent.local",
                "display_name": "Admin",
                "created_at": now_str,
            },
        )

    # Create default membership if not exists
    res_mem = bind.execute(
        sa.text("SELECT id FROM memberships WHERE org_id = :org_id AND user_id = :user_id"),
        {"org_id": org_id, "user_id": DEFAULT_USER_ID},
    ).first()

    if not res_mem:
        now_str = datetime.now(timezone.utc).isoformat()
        bind.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, created_at) "
                "VALUES (:id, :org_id, :user_id, 'owner', :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "user_id": DEFAULT_USER_ID,
                "created_at": now_str,
            },
        )

    # 3. Update existing records in all business tables to default org_id
    for table in BUSINESS_TABLES:
        bind.execute(
            sa.text(f"UPDATE {table} SET org_id = :org_id WHERE org_id IS NULL"),
            {"org_id": org_id},
        )

        # Assert no NULL org_id remains
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE org_id IS NULL")).scalar()
        if count and count > 0:
            raise RuntimeError(
                f"Migration error: table {table} has {count} NULL org_id rows after backfill"
            )

    # 4. Enforce NOT NULL, create index, and add Foreign Keys for org_id and created_by_user_id
    for table in BUSINESS_TABLES:
        indexes = [idx["name"] for idx in inspector.get_indexes(table)]
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("org_id", existing_type=sa.String(length=36), nullable=False)
            if f"ix_{table}_org_id" not in indexes:
                batch_op.create_index(f"ix_{table}_org_id", ["org_id"])
            batch_op.create_foreign_key(
                f"fk_{table}_org_id", "organizations", ["org_id"], ["id"], ondelete="CASCADE"
            )
            batch_op.create_foreign_key(
                f"fk_{table}_created_by_user_id", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL"
            )

    # 5. Shift unique constraints on agent, provider, workflow, mcp_server to composite per-tenant (org_id, ...)
    with op.batch_alter_table("agents") as batch_op:
        batch_op.create_unique_constraint("uq_agents_org_name", ["org_id", "name"])

    with op.batch_alter_table("providers") as batch_op:
        batch_op.create_unique_constraint("uq_providers_org_key", ["org_id", "key"])
        batch_op.create_unique_constraint("uq_providers_org_name", ["org_id", "name"])

    with op.batch_alter_table("workflows") as batch_op:
        batch_op.create_unique_constraint("uq_workflows_org_name", ["org_id", "name"])

    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.create_unique_constraint("uq_mcp_servers_org_name", ["org_id", "name"])


def downgrade() -> None:
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_constraint("uq_mcp_servers_org_name", type_="unique")

    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_constraint("uq_workflows_org_name", type_="unique")

    with op.batch_alter_table("providers") as batch_op:
        batch_op.drop_constraint("uq_providers_org_name", type_="unique")
        batch_op.drop_constraint("uq_providers_org_key", type_="unique")

    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_constraint("uq_agents_org_name", type_="unique")

    for table in BUSINESS_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_created_by_user_id", type_="foreignkey")
            batch_op.drop_constraint(f"fk_{table}_org_id", type_="foreignkey")
            batch_op.drop_index(f"ix_{table}_org_id")
            batch_op.drop_column("created_by_user_id")
            batch_op.drop_column("org_id")
