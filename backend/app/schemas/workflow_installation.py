from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InstallationSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["hourly", "daily", "weekdays", "weekly", "event"] = "daily"
    time: str | None = Field(default="07:30", pattern=r"^\d{2}:\d{2}$")
    interval_hours: int | None = Field(default=None, ge=1, le=12)
    weekday: int | None = Field(default=None, ge=0, le=6)

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("time must be a valid 24-hour HH:MM value") from exc
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> InstallationSchedule:
        if self.kind in {"daily", "weekdays", "weekly"} and self.time is None:
            raise ValueError("time is required for calendar schedules")
        if self.kind == "hourly" and self.interval_hours is None:
            self.interval_hours = 1
        return self


class InstallationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(min_length=3, max_length=96)
    name: str | None = Field(default=None, max_length=160)
    timezone: str = Field(default="Asia/Ho_Chi_Minh", min_length=1, max_length=64)
    schedule: InstallationSchedule = Field(default_factory=InstallationSchedule)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


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
