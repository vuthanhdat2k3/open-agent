from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

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
    supports_vision: bool | None = None

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v: Any) -> str:
        if v == "fast":
            return "economy"
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in {"frontier", "balanced", "economy"}:
                return v_lower
        return "balanced"


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
    supports_vision: bool | None = None

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v: Any) -> str | None:
        if v is None:
            return None
        if v == "fast":
            return "economy"
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in {"frontier", "balanced", "economy"}:
                return v_lower
        return "balanced"


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

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier(cls, v: Any) -> str:
        if v == "fast":
            return "economy"
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in {"frontier", "balanced", "economy"}:
                return v_lower
        return "balanced"


class ModelTestResult(BaseModel):
    ok: bool
    latency_ms: int
    message: str
    sample_response: str | None = None
    model_name: str | None = None


class OrgModelTierConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    tier: Tier
    model_id: str | None = None
    model: ModelOut | None = None
    updated_at: datetime


class OrgModelTierMatrixUpdate(BaseModel):
    tier_mappings: dict[Tier, str | None]


class OrgModelTierMatrixResponse(BaseModel):
    tiers: dict[Tier, ModelOut | None]

