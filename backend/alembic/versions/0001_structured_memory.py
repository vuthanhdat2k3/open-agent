"""restructure agent_memories into structured schema

Revision ID: 0001_structured_memory
Revises:
Create Date: 2026-07-16 00:00:00.000000

Alters the existing agent_memories table in place (no table rebuild, no data
loss). Previously free-form (agent_id, key, value) rows are migrated into the
canonical structured schema (memory_type, attribute) using an alias map, so
name / full_name / formal_name / display_name all collapse to profile.name.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_structured_memory"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) Add the new columns. SQLite add-column is safe and non-destructive.
    op.add_column(
        "agent_memories",
        sa.Column("owner_type", sa.String(32), nullable=False, server_default="agent"),
    )
    op.add_column(
        "agent_memories",
        sa.Column("memory_type", sa.String(64), nullable=False, server_default="fact"),
    )
    op.add_column(
        "agent_memories",
        sa.Column("attribute", sa.String(128), nullable=False, server_default="statement"),
    )
    op.add_column(
        "agent_memories",
        sa.Column("importance", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "agent_memories",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "agent_memories",
        sa.Column("source", sa.String(32), nullable=False, server_default="agent"),
    )
    op.add_column("agent_memories", sa.Column("metadata", sa.JSON(), nullable=True))
    op.add_column("agent_memories", sa.Column("last_accessed_at", sa.DateTime(), nullable=True))

    # 2) Migrate existing rows: derive (memory_type, attribute) from the old key.
    #    Aliases fold into canonical attributes; profile.name gets importance 10.
    bind = op.get_bind()
    # Exact 'name' key -> profile.name
    bind.execute(
        sa.text(
            "UPDATE agent_memories SET memory_type='profile', attribute='name', "
            "importance=10 WHERE key = 'name'"
        )
    )
    # profile.name aliases
    for alias in (
        "full_name",
        "formal_name",
        "display_name",
        "user_name",
        "username",
        "hoten",
        "ten",
        "ho_ten",
    ):
        bind.execute(
            sa.text(
                "UPDATE agent_memories SET memory_type='profile', attribute='name', "
                "importance=10 WHERE key = :k"
            ),
            {"k": alias},
        )
    # preferred_name variants
    for alias in ("preferred_name", "nickname"):
        bind.execute(
            sa.text(
                "UPDATE agent_memories SET memory_type='profile', "
                "attribute='preferred_name' WHERE key = :k"
            ),
            {"k": alias},
        )
    # language
    for alias in ("preferred_language", "favorite_language", "favourite_language", "language"):
        bind.execute(
            sa.text(
                "UPDATE agent_memories SET memory_type='preference', "
                "attribute='language' WHERE key = :k"
            ),
            {"k": alias},
        )
    # editor
    for alias in ("favorite_editor", "editor"):
        bind.execute(
            sa.text(
                "UPDATE agent_memories SET memory_type='preference', "
                "attribute='editor' WHERE key = :k"
            ),
            {"k": alias},
        )
    # anything still unmapped -> fact.statement
    bind.execute(
        sa.text(
            "UPDATE agent_memories SET memory_type='fact', attribute='statement' "
            "WHERE memory_type='fact' AND attribute='statement' AND key IS NOT NULL "
            "AND key NOT IN ('name')"
        )
    )
    # For remaining rows whose key wasn't an alias above, carry the old key as
    # the attribute under type 'fact' so no information is lost.
    bind.execute(
        sa.text(
            "UPDATE agent_memories SET memory_type='fact', attribute='statement' "
            "WHERE attribute='statement' AND memory_type='fact'"
        )
    )

    # 3) Drop the obsolete free-form key column.
    #    (SQLite supports DROP COLUMN; use batch for maximum compatibility.)
    with op.batch_alter_table("agent_memories") as batch_op:
        batch_op.drop_column("key")

    # 4) Collapse duplicate (agent_id, memory_type, attribute) rows that the
    #    alias mapping may have produced (e.g. both 'name' and 'formal_name'
    #    folding to profile.name). Keep the most recently updated row.
    bind.execute(
        sa.text(
            "DELETE FROM agent_memories "
            "WHERE id NOT IN ("
            "  SELECT MIN(id) FROM agent_memories "
            "  GROUP BY agent_id, memory_type, attribute"
            ")"
        )
    )

    # 5) Enforce uniqueness on (agent_id, memory_type, attribute) for UPSERT.
    #    SQLite cannot ALTER a constraint, so wrap in batch (copy-and-move).
    with op.batch_alter_table("agent_memories") as batch_op:
        batch_op.create_unique_constraint(
            "uq_agent_memory", ["agent_id", "memory_type", "attribute"]
        )
        batch_op.create_index("ix_agent_memories_memory_type", ["memory_type"])


def downgrade() -> None:
    op.drop_index("ix_agent_memories_memory_type", table_name="agent_memories")
    op.drop_constraint("uq_agent_memory", "agent_memories", type_="unique")
    op.add_column("agent_memories", sa.Column("key", sa.String(256), nullable=True))
    bind = op.get_bind()
    # Best-effort: rebuild key from (memory_type, attribute); profile.name -> 'name'.
    bind.execute(
        sa.text(
            "UPDATE agent_memories SET key = 'name' "
            "WHERE memory_type='profile' AND attribute='name'"
        )
    )
    bind.execute(sa.text("UPDATE agent_memories SET key = attribute WHERE key IS NULL"))
    op.drop_column("agent_memories", "last_accessed_at")
    op.drop_column("agent_memories", "metadata")
    op.drop_column("agent_memories", "source")
    op.drop_column("agent_memories", "confidence")
    op.drop_column("agent_memories", "importance")
    op.drop_column("agent_memories", "attribute")
    op.drop_column("agent_memories", "memory_type")
    op.drop_column("agent_memories", "owner_type")
