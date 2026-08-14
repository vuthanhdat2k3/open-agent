from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkflowCatalogRecommendation(BaseModel):
    recommended: bool
    reason_code: str | None = None
    params: dict[str, Any] = {}


class WorkflowCatalogCapabilities(BaseModel):
    can_view: bool = True
    can_install: bool = False


class WorkflowCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    version: int
    name: str
    description: str
    outcome: str
    category: str
    icon: str
    required_integrations: list[str]
    optional_integrations: list[str]
    default_schedule_label: str
    cost_tier: str
    estimated_cost_usd: dict[str, Any]
    side_effect_policy: str
    recommendation: WorkflowCatalogRecommendation
    installed: bool = False
    capabilities: WorkflowCatalogCapabilities = WorkflowCatalogCapabilities()
    blocked_reasons: dict[str, list[str]] = {}


class WorkflowCatalogMeta(BaseModel):
    server_time: datetime
    next_cursor: str | None = None


class WorkflowCatalogResponse(BaseModel):
    data: list[WorkflowCatalogItem]
    meta: WorkflowCatalogMeta
