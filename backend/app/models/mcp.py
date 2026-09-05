from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now


class McpServer(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_mcp_servers_org_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), default="stdio", nullable=False)
    command: Mapped[str] = mapped_column(String(512), default="")
    args: Mapped[list[str]] = mapped_column(JSON, default=list)
    env: Mapped[dict] = mapped_column(JSON, default=dict)
    url: Mapped[str] = mapped_column(String(512), default="")
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    connection_status: Mapped[str] = mapped_column(String(32), default="disconnected")

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    tools: Mapped[list["McpTool"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )


class McpTool(Base):
    __tablename__ = "mcp_tools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # MCP tools are untrusted until explicitly classified. Existing rows are
    # backfilled to dangerous + approval-required by migration.
    risk_tier: Mapped[str] = mapped_column(String(32), default="dangerous", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    server: Mapped["McpServer"] = relationship(back_populates="tools")
