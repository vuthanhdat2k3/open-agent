from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentBase(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model_id: str
    tools: list[str] = []
    allowed_risk_tiers: list[str] | None = None
    max_iterations: int = 12
    temperature: float = 0.7


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model_id: str | None = None
    tools: list[str] | None = None
    allowed_risk_tiers: list[str] | None = None
    max_iterations: int | None = None
    temperature: float | None = None


class AgentToolInfo(BaseModel):
    name: str
    description: str
    available: bool


class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
