from datetime import datetime

from app.workflows.scheduler import next_run_at


def test_event_workflow_has_no_scheduled_occurrence():
    assert next_run_at({"kind": "event", "time": "07:30"}, "Asia/Ho_Chi_Minh", now=datetime(2026, 8, 14, 0, 0)) is None
