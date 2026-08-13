from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"


def normalize_timezone(value: str | None) -> str:
    name = (value or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        return DEFAULT_TIMEZONE
    return name


def now_in_timezone(timezone_name: str | None = None) -> datetime:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(normalize_timezone(timezone_name)))


def build_runtime_context(timezone_name: str | None = None) -> str:
    zone_name = normalize_timezone(timezone_name)
    current = now_in_timezone(zone_name)
    return (
        "Runtime date/time context (authoritative for this run):\n"
        f"- Current UTC: {current.astimezone(timezone.utc).isoformat()}\n"
        f"- User timezone: {zone_name}\n"
        f"- User local time: {current.isoformat()}\n"
        f"- Local date: {current.strftime('%A, %Y-%m-%d')}\n"
        "Use this context for relative dates. Do not infer the current date from "
        "model knowledge. For exact time after a long operation, call get_current_time."
    )
