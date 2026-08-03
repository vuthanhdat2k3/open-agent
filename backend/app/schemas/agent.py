from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentBase(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model_id: str
    tools: list[str] = Field(default_factory=list)
    allowed_risk_tiers: list[str] | None = None
    kind: Literal["worker", "orchestrator"] = "worker"
    max_iterations: int = 12
    temperature: float = 0.7
    a2a_exposed: bool = False


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model_id: str | None = None
    tools: list[str] | None = None
    allowed_risk_tiers: list[str] | None = None
    kind: Literal["worker", "orchestrator"] | None = None
    max_iterations: int | None = None
    temperature: float | None = None
    a2a_exposed: bool | None = None


class AgentToolInfo(BaseModel):
    name: str
    description: str
    available: bool
    risk_tier: str | None = None


class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    model_id: str | None = None
    id: str
    a2a_exposed: bool = False
    active_release_id: str | None = None
    latest_release_number: int = 0
    created_at: datetime
    updated_at: datetime


class AgentReleaseCreate(BaseModel):
    description: str | None = None
    system_prompt: str | None = None
    model_id: str | None = None
    tools: list[str] | None = None
    allowed_risk_tiers: list[str] | None = None
    kind: Literal["worker", "orchestrator"] | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    change_note: str = Field(default="", max_length=512)


class AgentReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    version: int
    status: Literal["draft", "published", "archived"]
    description: str
    system_prompt: str
    model_id: str
    tools: list[str]
    allowed_risk_tiers: list[str]
    kind: Literal["worker", "orchestrator"]
    max_iterations: int
    temperature: float
    change_note: str
    config_hash: str
    created_by_user_id: str | None
    published_by_user_id: str | None
    created_at: datetime
    published_at: datetime | None
    quality_gate_status: str
    quality_gate_run_id: str | None
