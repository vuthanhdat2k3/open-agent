from app.core.workflow.engine import _eval_condition


def test_workflow_condition_allows_safe_expression() -> None:
    assert _eval_condition("'ok' in output", "status=ok")


def test_workflow_condition_rejects_malicious_expression() -> None:
    assert not _eval_condition("__import__('os').system('echo bad')", "")

