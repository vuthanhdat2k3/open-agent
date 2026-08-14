from datetime import datetime, timezone, timedelta

from app.customer_intelligence.workflow import _persistable_utc_datetime


def test_persistable_datetime_converts_offset_to_naive_utc():
    value = datetime(2026, 8, 15, 17, 0, tzinfo=timezone(timedelta(hours=7)))

    result = _persistable_utc_datetime(value)

    assert result == datetime(2026, 8, 15, 10, 0)
    assert result.tzinfo is None


def test_persistable_datetime_keeps_naive_utc_compatibility():
    value = datetime(2026, 8, 15, 10, 0)

    assert _persistable_utc_datetime(value) == value


def test_persistable_datetime_accepts_missing_value():
    assert _persistable_utc_datetime(None) is None
