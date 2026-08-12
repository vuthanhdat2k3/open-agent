from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.providers.constants import DEFAULT_CONTEXT_WINDOW

Tier = Literal["frontier", "balanced", "economy"]


class ModelBase(BaseModel):
    provider_id: str
    name: str
    display_name: str
    tier: Tier = "balanced"
    context_window: int = DEFAULT_CONTEXT_WINDOW
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    active: bool = True
    enabled: bool | None = None


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
    enabled: bool | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    name: str
    display_name: str
    tier: Tier
    context_window: int
    input_cost_per_1k: float
    output_cost_per_1k: float
    active: bool
    enabled: bool
    discovered: bool
    source: str
    last_seen_at: datetime | None = None
    catalog_source: str | None = None
    catalog_version: str | None = None
    last_discovered_at: datetime | None = None
    supports_tools: bool | None = None
    supports_reasoning: bool | None = None
    supports_vision: bool | None = None
    created_at: datetime
