from __future__ import annotations

from typing import Any

from app.core.tools.registry import execute_tool_call
from app.core.tools.types import ToolContext, ToolSpec


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

    result = await execute_tool_call(spec, {}, ToolContext(db=None))  # type: ignore[arg-type]

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
        ToolContext(db=None),  # type: ignore[arg-type]
    )

    assert result == "read ok.txt"

