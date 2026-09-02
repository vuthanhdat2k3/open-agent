from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.core.execution_policy import ExecutionPolicy

ChatRole = Literal["user", "assistant", "system", "tool"]


class ChatRequest(BaseModel):
    agent_id: str
    # Optional per-chat model override. The backend validates organization and
    # active status for user selections; it never changes the agent default.
    model_id: str | None = None
    message: str
    session_id: str | None = None
    run_id: str | None = None
    stream: bool = True
    timezone: str | None = None
    execution_policy: ExecutionPolicy | None = None


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
    execution_policy: ExecutionPolicy
    title: str
    created_at: datetime
    updated_at: datetime


class SessionUpdate(BaseModel):
    execution_policy: ExecutionPolicy | None = None
    title: str | None = None


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
    cost_usd: float = 0.0
    error: str | None = None
