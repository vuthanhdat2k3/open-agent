from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ChannelProvider = Literal["telegram", "discord"]


class ChannelConnectionBase(BaseModel):
    provider: ChannelProvider
    bot_username: str = ""
    config: dict[str, Any] = {}


class ChannelConnectionCreate(BaseModel):
    provider: ChannelProvider
    bot_token: str
    bot_username: str = ""
    config: dict[str, Any] = {}


class ChannelConnectionUpdate(BaseModel):
    bot_token: str | None = None
    bot_username: str | None = None
    config: dict[str, Any] | None = None
    status: str | None = None


class ChannelConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    provider: ChannelProvider
    bot_username: str = ""
    status: str = "active"
    config: dict[str, Any] = {}
    created_by_user_id: str | None = None
    latest_session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    connection_id: str
    direction: str
    external_message_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    conversation_id: str = ""
    message_type: str = "text"
    content: str = ""
    metadata: dict[str, Any] = {}
    agent_id: str | None = None
    created_at: datetime


class ChannelTestResponse(BaseModel):
    ok: bool
    message: str
