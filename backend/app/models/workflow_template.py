from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    versions: Mapped[list[WorkflowTemplateVersion]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="WorkflowTemplateVersion.version"
    )


class WorkflowTemplateVersion(Base):
    __tablename__ = "workflow_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_workflow_template_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    icon: Mapped[str] = mapped_column(String(64), nullable=False, default="zap")
    required_integrations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    optional_integrations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    default_schedule_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    cost_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    estimated_cost_usd: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    side_effect_policy: Mapped[str] = mapped_column(String(48), nullable=False, default="approval_required")
    recommendation_reason_code: Mapped[str | None] = mapped_column(String(96), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    template: Mapped[WorkflowTemplate] = relationship(back_populates="versions")
