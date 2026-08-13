from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class EmailConnection(Base):
    __tablename__ = "ci_connections"
    __table_args__ = (UniqueConstraint("org_id", "account_email", name="uq_ci_conn_org_account"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)  # gmail
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="disconnected")  # connected|disconnected|error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_cursor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gmail_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    watch_expiration_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    watch_resource_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CalendarConnection(Base):
    __tablename__ = "ci_calendar_connections"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", "account_email", name="uq_ci_calendar_org_provider_account"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)  # google
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="disconnected")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DriveConnection(Base):
    __tablename__ = "ci_drive_connections"
    __table_args__ = (
        UniqueConstraint("org_id", "account_email", name="uq_ci_drive_org_account"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="google")
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="disconnected")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class InboundEmail(Base):
    __tablename__ = "ci_emails"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "provider", "provider_message_id", name="uq_ci_email_org_provider_msg"
        ),
        Index("ix_ci_emails_org_received_id", "org_id", "received_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ci_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(256), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(320), nullable=True)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    sender_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    injection_flags: Mapped[list] = mapped_column(JSON, default=list)
    classification: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    routing_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class CiNotification(Base):
    __tablename__ = "ci_notifications"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", "email_id", "notification_type", name="uq_ci_notification_email_type"),
        Index("ix_ci_notifications_user_created_id", "user_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(320), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class CiTrustedRule(Base):
    __tablename__ = "ci_trusted_rules"
    __table_args__ = (UniqueConstraint("org_id", "name", "version", name="uq_ci_trusted_rule_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False, index=True)
    match_type: Mapped[str] = mapped_column(String(24), nullable=False)
    match_value: Mapped[str] = mapped_column(String(320), nullable=False)
    action_type: Mapped[str] = mapped_column(String(48), default="CALENDAR_AUTO_CREATE", nullable=False)
    calendar_connection_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ci_calendar_connections.id", ondelete="SET NULL"), nullable=True)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), default="2026-08-13.1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class CiPublicEmailDomain(Base):
    __tablename__ = "ci_public_email_domains"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    registry_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class CiAutomationBudget(Base):
    __tablename__ = "ci_automation_budgets"
    __table_args__ = (UniqueConstraint("scope_type", "scope_id", "budget_date", name="uq_ci_automation_budget_scope_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    budget_date: Mapped[str] = mapped_column(String(10), nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    budget_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class ResearchCase(Base):
    __tablename__ = "ci_cases"
    __table_args__ = (UniqueConstraint("org_id", "email_id", name="uq_ci_case_org_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ci_connections.id", ondelete="SET NULL"), nullable=True
    )
    calendar_connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ci_calendar_connections.id", ondelete="SET NULL", name="fk_ci_cases_calendar_connection"), nullable=True
    )
    company_name: Mapped[str | None] = mapped_column(String(320), nullable=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NEW", nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trigger: Mapped[str | None] = mapped_column(String(24), nullable=True)  # manual|daily|webhook
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_retry_triggered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ResearchSource(Base):
    __tablename__ = "ci_sources"
    __table_args__ = (
        UniqueConstraint("org_id", "case_id", "url", name="uq_ci_source_case_url"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # website|news|company|calendar
    title: Mapped[str] = mapped_column(Text, default="")
    publisher: Mapped[str | None] = mapped_column(String(320), nullable=True)
    published_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieved_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Meeting(Base):
    __tablename__ = "ci_meetings"
    __table_args__ = (
        UniqueConstraint("org_id", "case_id", "provider_event_id", name="uq_ci_meeting_case_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_event_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attendees: Mapped[list] = mapped_column(JSON, default=list)
    organizer: Mapped[str | None] = mapped_column(String(320), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)  # confirmed_match|possible_match
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_on: Mapped[list] = mapped_column(JSON, default=list)


class BriefingReport(Base):
    __tablename__ = "ci_reports"
    __table_args__ = (
        UniqueConstraint("org_id", "case_id", "version", name="uq_ci_report_case_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    canonical_markdown: Mapped[str] = mapped_column(Text, default="")
    rendering: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # html/pdf/docx refs
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_delivery_org_idemkey"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # send_email|save_knowledge
    provider_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ci_connections.id", ondelete="SET NULL"), nullable=True
    )
    provider_draft_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_send_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # draft|delivered|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class CiSchedule(Base):
    __tablename__ = "ci_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    run_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class GmailNotification(Base):
    __tablename__ = "ci_gmail_notifications"
    __table_args__ = (
        UniqueConstraint("connection_id", "history_id", name="uq_ci_gmail_notification_history"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ci_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    history_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_notification_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="received", nullable=False)
