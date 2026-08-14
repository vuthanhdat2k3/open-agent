from datetime import datetime

import pytest

from app.schemas.workflow_installation import InstallationCreate
from app.workflows.scheduler import next_run_at


def test_event_workflow_has_no_scheduled_occurrence():
    assert next_run_at({"kind": "event", "time": "07:30"}, "Asia/Ho_Chi_Minh", now=datetime(2026, 8, 14, 0, 0)) is None


def test_installation_rejects_invalid_timezone() -> None:
    with pytest.raises(ValueError, match="valid IANA timezone"):
        InstallationCreate(timezone="Not/AZone")


def test_installation_rejects_invalid_clock_time() -> None:
    with pytest.raises(ValueError, match="valid 24-hour"):
        InstallationCreate(schedule={"kind": "daily", "time": "25:00"})
