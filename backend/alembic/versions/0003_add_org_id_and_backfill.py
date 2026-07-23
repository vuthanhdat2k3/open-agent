"""add org_id to business tables, backfill default org, enforce NOT NULL

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

    # 1. Add nullable org_id and created_by_user_id to business tables
    for table in BUSINESS_TABLES:
        op.add_column(table, sa.Column("org_id", sa.String(length=36), nullable=True))
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

    # 4. Enforce NOT NULL and create index for org_id
    for table in BUSINESS_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("org_id", existing_type=sa.String(length=36), nullable=False)
            batch_op.create_index(f"ix_{table}_org_id", ["org_id"])


def downgrade() -> None:
    for table in BUSINESS_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f"ix_{table}_org_id")
            batch_op.drop_column("created_by_user_id")
            batch_op.drop_column("org_id")
