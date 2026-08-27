"""Edge condition logging (Fix #2) and resume data binding (Fix #1).

Both fixes preserve existing behavior — guardrail tests already assert
``_eval_condition`` returns False for hostile expressions, and the resume
path still rebuilds ``NodeOutput`` from the checkpoint dict. The new
behavior is:
- Bad-syntax conditions now log a warning (structlog event
  ``workflow_edge_condition_failed``) before returning False.
- A non-dict checkpoint (legacy / non-structured) still produces a
  ``NodeOutput`` with empty data, which makes downstream
  ``output_data``/``output_<key>`` references evaluate to None and the
  condition log line up clearly, instead of silently skipping branches.
"""
from __future__ import annotations

from app.core.workflow.engine import _eval_condition
from app.schemas.workflow import NodeOutput


def test_eval_condition_returns_false_for_hostile_expression() -> None:
    """Existing guardrail — preserved on purpose."""
    hostile = "__import__('os').system('echo bad')"
    assert _eval_condition(hostile, "") is False


def test_eval_condition_returns_false_for_bad_syntax() -> None:
    """Bad syntax evaluates to False (this is the behavior the new log line
    advertises)."""
    assert _eval_condition("output.category =", "urgent") is False


def test_eval_condition_logs_warning_on_bad_syntax(capsys) -> None:
    """Fix #2: surface the failure so an operator can fix a typo'd
    condition instead of debugging a silent skip in the downstream node.

    structlog writes JSON to stdout; we don't try to route it through
    Python's logging root. The test just asserts the warning event is
    present in the captured output.
    """
    _eval_condition("output.category =", "urgent")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "workflow_edge_condition_failed" in combined, (
        f"expected the warning event, got stdout={captured.out!r} stderr={captured.err!r}"
    )
    # The condition and error type should also be present so an operator
    # can see at a glance which edge failed.
    assert "output.category =" in combined
    assert "SyntaxError" in combined


def test_eval_condition_still_works_for_valid_expressions() -> None:
    """No regression on the happy path."""
    assert _eval_condition("'ok' in output", "status=ok") is True
    assert _eval_condition("'ok' in output", "chill email") is False


def test_eval_condition_handles_structured_node_output() -> None:
    out = NodeOutput(text="sales email", data={"category": "sales"})
    assert _eval_condition("output.category == 'sales'", out) is True
    assert _eval_condition("output.category == 'support'", out) is False
    assert _eval_condition("output_text == 'sales email'", out) is True
