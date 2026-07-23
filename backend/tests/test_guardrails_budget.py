from app.core.guardrails.budget import BudgetTracker, RunBudget


def test_budget_tracker_stops_repeated_identical_calls() -> None:
    tracker = BudgetTracker(RunBudget(max_repeated_call=3))

    for _ in range(3):
        assert tracker.record_call("read_attachment", {"path": "same.txt"}) is None

    reason = tracker.record_call("read_attachment", {"path": "same.txt"})
    assert reason is not None
    assert "max_repeated_call exceeded" in reason


def test_budget_tracker_stops_total_tool_calls() -> None:
    tracker = BudgetTracker(RunBudget(max_tool_calls=2))

    assert tracker.record_call("a", {}) is None
    assert tracker.record_call("b", {}) is None
    assert "max_tool_calls exceeded" in (tracker.record_call("c", {}) or "")

