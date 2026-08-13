"""Add Smart Inbox sort and search indexes."""

from __future__ import annotations

from alembic import op

revision = "0036_smart_inbox_indexes"
down_revision = "0035_trusted_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ci_emails_org_received_id",
        "ci_emails",
        ["org_id", "received_at", "id"],
    )
    op.create_index(
        "ix_ci_notifications_user_created_id",
        "ci_notifications",
        ["user_id", "created_at", "id"],
    )
    op.execute(
        "CREATE INDEX ix_ci_notifications_user_unread_created ON ci_notifications "
        "(user_id, created_at DESC, id DESC) WHERE read_at IS NULL"
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    # PostgreSQL's trigram indexes keep contains-search on inbox text bounded
    # without introducing a separate search service.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_ci_emails_sender_trgm ON ci_emails USING gin (sender_email gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_ci_emails_subject_trgm ON ci_emails USING gin (subject gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_ci_notifications_title_trgm ON ci_notifications USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_ci_notifications_body_trgm ON ci_notifications USING gin (body gin_trgm_ops)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_ci_notifications_body_trgm")
        op.execute("DROP INDEX IF EXISTS ix_ci_notifications_title_trgm")
        op.execute("DROP INDEX IF EXISTS ix_ci_emails_subject_trgm")
        op.execute("DROP INDEX IF EXISTS ix_ci_emails_sender_trgm")
    op.execute("DROP INDEX IF EXISTS ix_ci_notifications_user_unread_created")
    op.drop_index("ix_ci_notifications_user_created_id", table_name="ci_notifications")
    op.drop_index("ix_ci_emails_org_received_id", table_name="ci_emails")
