from datetime import datetime
from typing import Any, Literal, Optional

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
    name: Optional[str] = None
    transport: Optional[Transport] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[dict[str, str]] = None


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
