from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrganizationQuotaUpdate(BaseModel):
    requests_per_minute: int | None = Field(default=None, ge=1, le=1_000_000)
    agent_runs_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    max_concurrent_runs: int | None = Field(default=None, ge=1, le=10_000)
    monthly_cost_usd: float | None = Field(default=None, ge=0, le=1_000_000_000)
    max_agents: int | None = Field(default=None, ge=1, le=1_000_000)
    max_workflows: int | None = Field(default=None, ge=1, le=1_000_000)
    max_storage_bytes: int | None = Field(default=None, ge=1)
    enforcement_mode: Literal["enforce", "observe"] | None = None


class OrganizationQuotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_id: str
    requests_per_minute: int
    agent_runs_per_minute: int
    max_concurrent_runs: int
    monthly_cost_usd: float
    max_agents: int | None
    max_workflows: int | None
    max_storage_bytes: int | None
    enforcement_mode: Literal["enforce", "observe"]
    updated_by_user_id: str | None
    created_at: datetime
    updated_at: datetime


class QuotaUsageOut(BaseModel):
    org_id: str
    month: str
    monthly_cost_usd: float
    monthly_cost_limit_usd: float
    agents: int
    agent_limit: int | None
    workflows: int
    workflow_limit: int | None
    storage_bytes: int
    storage_limit_bytes: int | None
    active_run_leases: int
    concurrent_run_limit: int
