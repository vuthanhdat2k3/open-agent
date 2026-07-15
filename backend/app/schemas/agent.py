from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AgentBase(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    model_id: str
    tools: list[str] = []
    max_iterations: int = 12
    temperature: float = 0.7


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[str] = None
    tools: Optional[list[str]] = None
    max_iterations: Optional[int] = None
    temperature: Optional[float] = None


class AgentToolInfo(BaseModel):
    name: str
    description: str
    available: bool


class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
