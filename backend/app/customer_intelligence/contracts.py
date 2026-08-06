from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, TypedDict

CaseStatus = Literal[
    "NEW",
    "INGESTED",
    "RESEARCHING",
    "REPORT_READY",
    "AWAITING_APPROVAL",
    "APPROVED",
    "EXECUTING",
    "COMPLETED",
    "REJECTED",
    "EXPIRED",
    "RETRYING",
    "DEAD_LETTER",
]


class ToolResult(TypedDict, total=False):
    """Typed result contract for every Customer Intelligence tool.

    ``status`` is one of ``ok`` | ``error`` | ``empty`` | ``research_unavailable``.
    ``sources`` carries provenance for every external claim; ``warnings`` records
    partial-failure notes without fabricating data.
    """

    status: Literal["ok", "error", "empty", "research_unavailable"]
    data: Any
    sources: list[dict[str, str]]
    warnings: list[str]
    confidence: float
    trace_id: str


@dataclass
class EmailAttachmentMeta:
    filename: str
    content_type: str
    size_bytes: int


@dataclass
class NormalizedEmail:
    provider: str
    provider_message_id: str
    thread_id: str | None
    sender_name: str | None
    sender_email: str
    sender_domain: str
    recipients: list[str]
    subject: str
    body_text: str
    body_html: str | None
    attachments: list[EmailAttachmentMeta]
    received_at: datetime
    headers: dict[str, str] = field(default_factory=dict)
    injection_flags: list[str] = field(default_factory=list)
    content_hash: str = ""


@dataclass
class SyncPage:
    messages: list[NormalizedEmail]
    new_cursor: str | None
    has_more: bool


@dataclass
class SearchHit:
    url: str
    title: str
    publisher: str
    published_date: str | None
    retrieved_date: str
    excerpt: str
    domain: str


@dataclass
class CompanyRecord:
    company_id: str
    canonical_name: str
    aliases: list[str]
    industry: str | None
    products: list[str]
    contacts: list[dict[str, str]]
    source: str
    updated_at: str | None
    domain: str | None = None


@dataclass
class CalendarEvent:
    provider_event_id: str
    title: str
    start_at: datetime
    end_at: datetime
    attendees: list[str]
    organizer: str | None
    description: str | None
    location: str | None


@dataclass
class MeetingMatch:
    event: CalendarEvent
    match_type: Literal["confirmed_match", "possible_match"]
    confidence: float
    matched_on: list[str]


class ReportSections(TypedDict, total=False):
    """Stable 7-section report schema (FR-006)."""

    executive_summary: str
    company_overview: list[dict[str, Any]]
    recent_news: list[dict[str, Any]]
    contact_information: list[dict[str, Any]]
    upcoming_meetings: list[dict[str, Any]]
    open_questions: list[str]
    sources: list[dict[str, Any]]


# --- Tool input JSON schemas (typed, allowlisted, bounded) -------------------
# Schemas double as the allowlist contract: the workflow only wires the tools
# below, and every spec bounds its inputs.

EMAIL_LIST_NEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cursor": {"type": "string", "description": "Opaque sync cursor from a previous page"},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
    },
    "additionalProperties": False,
}

EMAIL_GET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"provider_message_id": {"type": "string"}},
    "required": ["provider_message_id"],
    "additionalProperties": False,
}

EMAIL_CREATE_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "subject": {"type": "string", "maxLength": 500},
        "body": {"type": "string", "maxLength": 200_000},
        "in_reply_to": {"type": "string"},
    },
    "required": ["to", "subject", "body"],
    "additionalProperties": False,
}

EMAIL_SEND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {"type": "string"},
        "idempotency_key": {"type": "string", "maxLength": 128},
    },
    "required": ["draft_id", "idempotency_key"],
    "additionalProperties": False,
}

WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 300},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
    },
    "required": ["query"],
    "additionalProperties": False,
}

NEWS_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 300},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        "lookback_days": {"type": "integer", "enum": [7, 30, 90], "default": 30},
    },
    "required": ["query"],
    "additionalProperties": False,
}

WEB_FETCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"url": {"type": "string", "format": "uri", "maxLength": 2048}},
    "required": ["url"],
    "additionalProperties": False,
}

COMPANY_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
    },
    "required": ["query"],
    "additionalProperties": False,
}

COMPANY_GET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"company_id": {"type": "string", "maxLength": 128}},
    "required": ["company_id"],
    "additionalProperties": False,
}

CALENDAR_LIST_EVENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "from": {"type": "string", "format": "date-time"},
        "to": {"type": "string", "format": "date-time"},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25},
    },
    "required": ["from", "to"],
    "additionalProperties": False,
}

CALENDAR_GET_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"provider_event_id": {"type": "string", "maxLength": 128}},
    "required": ["provider_event_id"],
    "additionalProperties": False,
}

CALENDAR_CREATE_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "start": {"type": "string", "format": "date-time"},
        "end": {"type": "string", "format": "date-time"},
        "description": {"type": "string", "maxLength": 10000},
        "location": {"type": "string", "maxLength": 1000},
        "attendees": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
    },
    "required": ["summary", "start", "end"],
    "additionalProperties": False,
}

CALENDAR_UPDATE_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "provider_event_id": {"type": "string", "maxLength": 128},
        "summary": {"type": "string", "maxLength": 500},
        "start": {"type": "string", "format": "date-time"},
        "end": {"type": "string", "format": "date-time"},
        "description": {"type": "string", "maxLength": 10000},
        "location": {"type": "string", "maxLength": 1000},
        "attendees": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
    },
    "required": ["provider_event_id"],
    "additionalProperties": False,
}

CALENDAR_DELETE_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"provider_event_id": {"type": "string", "maxLength": 128}},
    "required": ["provider_event_id"],
    "additionalProperties": False,
}



DRIVE_LIST_FILES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "maxLength": 200},
        "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
    },
    "additionalProperties": False,
}

DRIVE_GET_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "maxLength": 256},
        "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000, "default": 50000},
    },
    "required": ["file_id"],
    "additionalProperties": False,
}

DRIVE_CREATE_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 255},
        "content": {"type": "string", "maxLength": 200000},
        "mime_type": {"type": "string", "maxLength": 128},
        "parent_id": {"type": "string", "maxLength": 256},
    },
    "required": ["name", "content"],
    "additionalProperties": False,
}

DRIVE_UPDATE_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "maxLength": 256},
        "content": {"type": "string", "maxLength": 200000},
        "name": {"type": "string", "maxLength": 255},
        "mime_type": {"type": "string", "maxLength": 128},
    },
    "required": ["file_id"],
    "additionalProperties": False,
}

DRIVE_DELETE_FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"file_id": {"type": "string", "maxLength": 256}},
    "required": ["file_id"],
    "additionalProperties": False,
}
