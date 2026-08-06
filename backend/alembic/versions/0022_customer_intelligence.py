"""customer intelligence: email-driven company research domain

Adds the persistence layer for the Customer Intelligence feature
(connections, inbound emails, research cases, sources, meetings, briefing
reports, delivery attempts, schedules) plus the approval fields required by
the human-approval flow (expiry, payload hash, idempotency key, case link).

Revision ID: 0022_customer_intelligence
Revises: 0021_chat_stream_recovery
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0022_customer_intelligence"
down_revision: str | None = "0021_chat_stream_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ci_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("credentials_enc", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="disconnected"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sync_cursor", sa.JSON(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "account_email", name="uq_ci_conn_org_account"),
    )
    op.create_index("ix_ci_connections_org_id", "ci_connections", ["org_id"])

    op.create_table(
        "ci_emails",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ci_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=256), nullable=False),
        sa.Column("thread_id", sa.String(length=256), nullable=True),
        sa.Column("sender_name", sa.String(length=320), nullable=True),
        sa.Column("sender_email", sa.String(length=320), nullable=False),
        sa.Column("sender_domain", sa.String(length=255), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("injection_flags", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "provider", "provider_message_id", name="uq_ci_email_org_provider_msg"
        ),
    )
    op.create_index("ix_ci_emails_org_id", "ci_emails", ["org_id"])
    op.create_index("ix_ci_emails_connection_id", "ci_emails", ["connection_id"])
    op.create_index("ix_ci_emails_received_at", "ci_emails", ["received_at"])
    op.create_index("ix_ci_emails_content_hash", "ci_emails", ["content_hash"])

    op.create_table(
        "ci_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "email_id",
            sa.String(length=36),
            sa.ForeignKey("ci_emails.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ci_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company_name", sa.String(length=320), nullable=True),
        sa.Column("company_domain", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NEW"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=True),
        sa.Column("trigger", sa.String(length=24), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "email_id", name="uq_ci_case_org_email"),
    )
    op.create_index("ix_ci_cases_org_id", "ci_cases", ["org_id"])
    op.create_index("ix_ci_cases_email_id", "ci_cases", ["email_id"])
    op.create_index("ix_ci_cases_status", "ci_cases", ["status"])

    op.create_table(
        "ci_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("ci_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("publisher", sa.String(length=320), nullable=True),
        sa.Column("published_date", sa.String(length=64), nullable=True),
        sa.Column("retrieved_date", sa.String(length=64), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("org_id", "case_id", "url", name="uq_ci_source_case_url"),
    )
    op.create_index("ix_ci_sources_org_id", "ci_sources", ["org_id"])
    op.create_index("ix_ci_sources_case_id", "ci_sources", ["case_id"])

    op.create_table(
        "ci_meetings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("ci_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_event_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_at", sa.DateTime(), nullable=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("attendees", sa.JSON(), nullable=False),
        sa.Column("organizer", sa.String(length=320), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("match_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("matched_on", sa.JSON(), nullable=False),
        sa.UniqueConstraint("org_id", "case_id", "provider_event_id", name="uq_ci_meeting_case_event"),
    )
    op.create_index("ix_ci_meetings_org_id", "ci_meetings", ["org_id"])
    op.create_index("ix_ci_meetings_case_id", "ci_meetings", ["case_id"])

    op.create_table(
        "ci_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("ci_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("canonical_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("rendering", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "case_id", "version", name="uq_ci_report_case_version"),
    )
    op.create_index("ix_ci_reports_org_id", "ci_reports", ["org_id"])
    op.create_index("ix_ci_reports_case_id", "ci_reports", ["case_id"])

    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.String(length=36),
            sa.ForeignKey("ci_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "provider_id",
            sa.String(length=36),
            sa.ForeignKey("ci_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_draft_id", sa.String(length=256), nullable=True),
        sa.Column("provider_send_id", sa.String(length=256), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_delivery_org_idemkey"),
    )
    op.create_index("ix_delivery_attempts_org_id", "delivery_attempts", ["org_id"])
    op.create_index("ix_delivery_attempts_case_id", "delivery_attempts", ["case_id"])

    op.create_table(
        "ci_schedules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(length=36),
            sa.ForeignKey("ci_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("run_time", sa.String(length=5), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ci_schedules_org_id", "ci_schedules", ["org_id"])
    op.create_index("ix_ci_schedules_connection_id", "ci_schedules", ["connection_id"])

    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "case_id",
                sa.String(length=36),
                sa.ForeignKey("ci_cases.id", ondelete="CASCADE", name="fk_approval_requests_case_id"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("payload_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch_op.create_index("ix_approval_requests_case_id", ["case_id"])
        batch_op.create_unique_constraint(
            "uq_approval_org_idempotency", ["org_id", "idempotency_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("approval_requests") as batch_op:
        batch_op.drop_constraint("uq_approval_org_idempotency", type_="unique")
        batch_op.drop_index("ix_approval_requests_case_id")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("payload_hash")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("case_id")

    op.drop_table("ci_schedules")
    op.drop_table("delivery_attempts")
    op.drop_table("ci_reports")
    op.drop_table("ci_meetings")
    op.drop_table("ci_sources")
    op.drop_table("ci_cases")
    op.drop_table("ci_emails")
    op.drop_table("ci_connections")
