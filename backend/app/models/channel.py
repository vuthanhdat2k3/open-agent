from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now


class ChannelConnection(Base):
    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", "bot_username", name="uq_channel_org_provider_username"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Owner of a personal connection. NULL means the connection is shared
    # org-wide (operator/admin created for everyone). Set means only this user
    # and admins can manage it.
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    bot_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    bot_username: Mapped[str] = mapped_column(String(128), default="")
    webhook_secret: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    messages: Mapped[list["ChannelMessage"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class ChannelMessage(Base):
    __tablename__ = "channel_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("channel_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(128), default="")
    sender_id: Mapped[str] = mapped_column(String(128), default="")
    sender_name: Mapped[str] = mapped_column(String(256), default="")
    conversation_id: Mapped[str] = mapped_column(String(128), default="")
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    content: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)

    connection: Mapped["ChannelConnection"] = relationship(back_populates="messages")
