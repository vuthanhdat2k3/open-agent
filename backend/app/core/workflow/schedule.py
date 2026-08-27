"""Schedule helpers for the workflow scheduler node.

Maps the visual scheduler-node parameters (frequency, time, days_of_week,
custom_cron, timezone) to the ``{kind, time, weekday, interval_hours}`` shape
consumed by ``app.workflows.scheduler.next_run_at`` and to a human-readable
cron label.
"""

from __future__ import annotations

from typing import Any

_WEEKDAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_WEEKDAY_CRON = {"mon": "1", "tue": "2", "wed": "3", "thu": "4", "fri": "5", "sat": "6", "sun": "0"}


def build_cron(
    *,
    frequency: str,
    time: str = "07:30",
    days_of_week: list[str] | None = None,
    custom_cron: str = "",
) -> tuple[str, str]:
    """Return ``(cron_expression, schedule_label)`` for the scheduler node.

    Raises ``ValueError`` for an invalid combination or an unparseable custom
    cron (5-field format).
    """
    days = days_of_week or []
    if frequency == "custom":
        cron = custom_cron.strip()
        if not cron:
            raise ValueError("custom cron expression is required")
        parts = cron.split()
        if len(parts) != 5:
            raise ValueError("custom cron must be a 5-field expression (e.g. '0 6 * * *')")
        return cron, f"Custom ({cron})"
    if frequency == "once":
        return "", "Once (manual trigger)"
    if frequency == "hourly":
        return "0 * * * *", "Every hour"
    hour, minute = _parse_time(time)
    if frequency == "daily":
        return f"{minute} {hour} * * *", f"Daily at {time}"
    if frequency == "weekdays":
        return f"{minute} {hour} * * 1-5", f"Weekdays at {time}"
    if frequency == "weekly":
        if not days:
            raise ValueError("weekly schedule requires at least one day of the week")
        cron_days = ",".join(_WEEKDAY_CRON[d] for d in days if d in _WEEKDAY_CRON)
        if not cron_days:
            raise ValueError("weekly schedule has no valid days")
        label_days = ", ".join(d.capitalize() for d in days)
        return f"{minute} {hour} * * {cron_days}", f"Weekly on {label_days} at {time}"
    raise ValueError(f"unknown frequency: {frequency}")


def to_schedule_dict(parameters: dict[str, Any]) -> dict[str, Any]:
    """Map scheduler-node parameters to the ``next_run_at`` schedule shape."""
    frequency = str(parameters.get("frequency") or "daily")
    time = str(parameters.get("time") or "07:30")
    days = list(parameters.get("days_of_week") or [])

    if frequency == "once":
        return {"kind": "once", "time": None, "weekday": None, "interval_hours": None}
    if frequency == "hourly":
        return {"kind": "hourly", "time": None, "weekday": None, "interval_hours": 1}
    if frequency == "custom":
        return {
            "kind": "custom",
            "cron": str(parameters.get("custom_cron") or "").strip(),
            "time": time,
            "weekday": None,
            "interval_hours": None,
        }
    if frequency == "weekdays":
        return {"kind": "weekdays", "time": time, "weekday": None, "interval_hours": None}
    if frequency == "weekly":
        weekday = _WEEKDAY_ORDER.index(days[0]) if days else 0
        return {"kind": "weekly", "time": time, "weekday": weekday, "interval_hours": None}
    return {"kind": "daily", "time": time, "weekday": None, "interval_hours": None}


def _parse_time(value: str) -> tuple[str, str]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid time: {value!r} (expected HH:MM)")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"invalid time: {value!r} (expected HH:MM)") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time: {value!r} (expected HH:MM)")
    return f"{hour:02d}", f"{minute:02d}"
