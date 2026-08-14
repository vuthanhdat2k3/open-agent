from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class InstallationSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["hourly", "daily", "weekdays", "weekly", "event"] = "daily"
    time: str | None = Field(default="07:30", pattern=r"^\d{2}:\d{2}$")
    interval_hours: int | None = Field(default=None, ge=1, le=12)
    weekday: int | None = Field(default=None, ge=0, le=6)


class InstallationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(min_length=3, max_length=96)
    name: str | None = Field(default=None, max_length=160)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", min_length=1, max_length=64)
    schedule: InstallationSchedule = Field(default_factory=InstallationSchedule)
    settings: dict[str, Any] = Field(default_factory=dict)


class InstallationCapabilities(BaseModel):
    can_view: bool = True
    can_pause: bool = True
    can_resume: bool = False
    can_delete: bool = True
    can_run_now: bool = False


class InstallationOut(BaseModel):
    id: str
    template_key: str
    template_version: int
    workflow_id: str
    name: str
    status: str
    timezone: str
    schedule: dict[str, Any]
    settings: dict[str, Any]
    created_at: Any
    updated_at: Any
    capabilities: InstallationCapabilities
    blocked_reasons: dict[str, list[str]] = Field(default_factory=dict)
