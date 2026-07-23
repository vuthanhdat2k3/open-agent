from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ChatRole = Literal["user", "assistant", "system", "tool"]


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    session_id: str | None = None
    stream: bool = True


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    meta: dict[str, Any] = {}
    position: int = 0
    created_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatStreamEvent(BaseModel):
    # message_start | token | tool_call | tool_result | message_done | error
    # retry | self_correct (self-correction loop)
    event: str
    data: dict[str, Any] = {}


class AgentLoopResult(BaseModel):
    content: str
    tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    latency_ms: int = 0
