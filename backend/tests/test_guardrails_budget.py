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


def test_add_cost_trips_max_cost_budget() -> None:
    tracker = BudgetTracker(RunBudget(max_cost_usd=2.0))

    assert tracker.add_cost(1.5) is None
    assert tracker.cost_usd == 1.5
    reason = tracker.add_cost(1.5)
    assert reason is not None
    assert "max_cost_usd exceeded" in reason


def test_add_cost_zero_or_negative_does_not_change_total() -> None:
    tracker = BudgetTracker(RunBudget(max_cost_usd=2.0))

    tracker.add_cost(0.5)
    tracker.add_cost(0.0)
    tracker.add_cost(-1.0)
    assert tracker.cost_usd == 0.5
    assert tracker.exceeded() is None


def test_record_call_with_cost_accumulates_into_same_pool() -> None:
    tracker = BudgetTracker(RunBudget(max_cost_usd=2.0))

    assert tracker.record_call("t", {}, cost_usd=1.8) is None
    reason = tracker.add_cost(0.5)
    assert reason is not None
    assert "max_cost_usd exceeded" in reason

