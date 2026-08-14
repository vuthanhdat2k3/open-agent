from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _valid_run_time(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        raise ValueError("run_time must be HH:MM") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("run_time must be HH:MM")
    return value


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["gmail"]
    account_email: str = Field(min_length=3, max_length=320)


class ConnectionStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["connected", "disconnected", "error"]
    error: str | None = None


class ConnectionResponse(BaseModel):
    id: str
    provider: str
    account_email: str
    status: str
    error: str | None = None
    has_credentials: bool = False
    last_sync_at: datetime | None = None
    created_at: datetime


class CalendarConnectionResponse(BaseModel):
    id: str
    provider: str
    account_email: str
    status: str
    error: str | None = None
    has_credentials: bool = False
    created_at: datetime


class DriveConnectionResponse(BaseModel):
    id: str
    provider: str
    account_email: str
    status: str
    error: str | None = None
    has_credentials: bool = False
    created_at: datetime


class ConnectionSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: Literal["manual", "daily", "webhook"] = "manual"
    max_messages: int = Field(default=20, ge=1, le=50)


class CaseSummary(BaseModel):
    id: str
    email_id: str
    company_name: str | None = None
    company_domain: str | None = None
    status: str
    confidence: float | None = None
    trigger: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ManualResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=2, max_length=320)
    company_domain: str | None = Field(default=None, max_length=255)
    question: str | None = Field(default=None, max_length=4000)


class SourceResponse(BaseModel):
    id: str
    url: str
    source_type: str
    title: str
    publisher: str | None = None
    published_date: str | None = None
    retrieved_date: str | None = None
    excerpt: str
    confidence: float | None = None


class MeetingResponse(BaseModel):
    id: str
    provider_event_id: str
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    attendees: list[str] = Field(default_factory=list)
    match_type: str
    confidence: float | None = None


class ReportResponse(BaseModel):
    id: str
    case_id: str
    version: int
    canonical_markdown: str
    rendering: dict[str, Any] | None = None
    confidence: float | None = None
    status: str
    created_at: datetime


class CaseDetail(CaseSummary):
    email: dict[str, Any] | None = None
    sources: list[SourceResponse] = Field(default_factory=list)
    meetings: list[MeetingResponse] = Field(default_factory=list)
    report: ReportResponse | None = None
    error: str | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=2000)


class ManualReviewResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["confirm_delivered", "not_delivered", "create_new_proposal", "dismiss"]
    reason: str = Field(default="", max_length=2000)


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str
    run_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = "UTC"
    enabled: bool = True

    @field_validator("run_time")
    @classmethod
    def validate_run_time(cls, value: str) -> str:
        return _valid_run_time(value) or value


class ScheduleResponse(BaseModel):
    id: str
    connection_id: str
    enabled: bool
    run_time: str
    timezone: str
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = None
    enabled: bool | None = None

    @field_validator("run_time")
    @classmethod
    def validate_run_time(cls, value: str | None) -> str | None:
        return _valid_run_time(value)


class SyncResult(BaseModel):
    connection_id: str
    synced: int
    deduplicated: int
    new_cases: int
    classification_queued: int = 0
    cursor: str | None = None
    warnings: list[str] = Field(default_factory=list)
    correlation_id: str | None = None


class DeliverActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["send_email", "save_knowledge"]
    to: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=512)
    body: str | None = None


class ApprovalOut(BaseModel):
    id: str
    case_id: str | None = None
    action: str | None = None
    status: str
    reason: str = ""
    requested_by: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    args_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
