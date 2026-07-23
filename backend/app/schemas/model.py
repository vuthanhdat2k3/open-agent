from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Tier = Literal["frontier", "balanced", "economy"]


class ModelBase(BaseModel):
    provider_id: str
    name: str
    display_name: str
    tier: Tier = "balanced"
    context_window: int = 8192
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    active: bool = True


class ModelCreate(ModelBase):
    pass


class ModelUpdate(BaseModel):
    provider_id: str | None = None
    name: str | None = None
    display_name: str | None = None
    tier: Tier | None = None
    context_window: int | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    active: bool | None = None


class ModelOut(ModelBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
