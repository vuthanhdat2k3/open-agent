from __future__ import annotations

from typing import Any

from app.core.tools.authorization import build_tool_authorization
from app.core.tools.registry import execute_tool_call
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec

ORG_ID = "org-tool-schema-validation-tests"


def _ctx() -> ToolContext:
    """A minimal but authorization-valid context.

    These tests exercise JSON-schema validation, not authorization, so they
    need a context that clears authorize_tool_call rather than a bare
    ToolContext(db=None) which now fails closed by design.
    """
    return ToolContext(
        db=None,  # type: ignore[arg-type]
        org_id=ORG_ID,
        authorization=build_tool_authorization(
            org_id=ORG_ID,
            user_id=None,
            user_role=None,
            agent_id=None,
            allowed_risk_tiers=[RiskTier.safe.value],
            run_id="run-tool-schema-validation-tests",
            principal_type="system",
        ),
    )


async def test_execute_tool_call_rejects_invalid_args_before_running() -> None:
    called = False

    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        nonlocal called
        called = True
        return "should not run"

    spec = ToolSpec(
        name="needs_path",
        description="requires path",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        run=_run,
    )

    result = await execute_tool_call(spec, {}, _ctx())

    assert result.startswith("error: invalid arguments")
    assert "'path' is a required property" in result
    assert not called


async def test_execute_tool_call_runs_valid_args() -> None:
    async def _run(args: dict[str, Any], ctx: ToolContext) -> str:
        return f"read {args['path']}"

    spec = ToolSpec(
        name="needs_path",
        description="requires path",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        run=_run,
    )

    result = await execute_tool_call(
        spec,
        {"path": "ok.txt"},
        _ctx(),
    )

    assert result == "read ok.txt"

