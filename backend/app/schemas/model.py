from datetime import datetime
from typing import Literal, Optional

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
    provider_id: Optional[str] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    tier: Optional[Tier] = None
    context_window: Optional[int] = None
    input_cost_per_1k: Optional[float] = None
    output_cost_per_1k: Optional[float] = None
    active: Optional[bool] = None


class ModelOut(ModelBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
