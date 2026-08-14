from datetime import datetime

from app.workflows.scheduler import next_run_at


def test_daily_schedule_uses_vietnam_timezone() -> None:
    result = next_run_at(
        {"kind": "daily", "time": "07:30"},
        "Asia/Ho_Chi_Minh",
        now=datetime(2026, 8, 14, 0, 0),
    )
    assert result == datetime(2026, 8, 14, 0, 30)


def test_weekdays_skips_weekend() -> None:
    result = next_run_at(
        {"kind": "weekdays", "time": "07:30"},
        "Asia/Ho_Chi_Minh",
        now=datetime(2026, 8, 14, 1, 0),
    )
    assert result == datetime(2026, 8, 17, 0, 30)


def test_event_schedule_has_no_cron_occurrence() -> None:
    assert next_run_at({"kind": "event"}, "Asia/Ho_Chi_Minh", now=datetime(2026, 8, 14)) is None
