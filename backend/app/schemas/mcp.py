from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Transport = Literal["stdio", "sse", "http"]


class McpServerBase(BaseModel):
    name: str
    transport: Transport = "stdio"
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    url: str = ""
    headers: dict[str, str] = {}


class McpServerCreate(McpServerBase):
    pass


class McpServerUpdate(BaseModel):
    name: str | None = None
    transport: Transport | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


class McpToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    server_id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = {}
    enabled: bool = True


class McpServerOut(McpServerBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_status: str = "disconnected"
    tools: list[McpToolOut] = []
    created_at: datetime
    updated_at: datetime
