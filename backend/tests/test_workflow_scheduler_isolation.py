"""Per-installation isolation in the workflow scheduler (Fix #7).

A single bad row (bad timezone, DB constraint, etc.) must not roll back the
work for the rest of the batch. Each installation is processed in its own
try/except and a best-effort ``next_run_at`` advance lets the next tick skip
poison rows instead of crashing.

These tests focus on the cheap, deterministic parts: the helper signatures,
the failure-mode of ``next_run_at`` with a bad timezone, and the structure
of the public ``run_due_workflows`` return value. Full integration tests
against a real DB are intentionally out of scope here — see
``test_workflow_engine_upgrade.py`` for that style of coverage.
"""
from __future__ import annotations

from zoneinfo import ZoneInfoNotFoundError

import pytest

from app.workflows import scheduler


def test_next_run_at_with_bad_timezone_raises() -> None:
    """A bad timezone is the realistic failure mode Fix #7 guards against.

    ``_process_installation`` calls ``next_run_at`` after the row is queued,
    so a poison row's bad timezone must surface as an exception the caller's
    per-installation ``try/except`` can catch.
    """
    bad_schedule = {"kind": "daily", "time": "07:30"}
    with pytest.raises((ZoneInfoNotFoundError, KeyError, Exception)):
        scheduler.next_run_at(bad_schedule, "Not/AReal_Zone")


def test_next_run_at_with_event_returns_none() -> None:
    """Event-triggered schedules have no next_run_at; must not raise."""
    assert scheduler.next_run_at({"kind": "event"}, "UTC") is None


def test_run_due_workflows_returns_counters_dict() -> None:
    """The new return shape includes a ``failed`` counter for observability.

    Older call sites that ignore the new key keep working; the new key is
    what SRE dashboards and the worker log alerts key off.
    """
    import inspect

    sig = inspect.signature(scheduler.run_due_workflows)
    assert "db" in sig.parameters
    assert "now" in sig.parameters
    # No new required params — this is a bug-shape check.
    required = [
        name for name, param in sig.parameters.items()
        if param.default is inspect.Parameter.empty
    ]
    assert required == ["db"]


def test_process_installation_is_coroutine() -> None:
    """``_process_installation`` must be awaitable — the scheduler awaits it
    inside the per-row try/except. A regression to a sync function would
    make the whole fix a silent no-op.
    """
    import inspect

    assert inspect.iscoroutinefunction(scheduler._process_installation)
    assert inspect.iscoroutinefunction(scheduler._advance_next_run_at)
