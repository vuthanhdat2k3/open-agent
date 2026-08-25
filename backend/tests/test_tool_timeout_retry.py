"""Tests for ToolSpec timeout_s / max_retries enforcement in execute_tool_call."""

from __future__ import annotations

import asyncio

import pytest

from app.core.tools.registry import ToolTimeoutError, execute_tool_call
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec


def _spec(name: str, run, *, timeout_s: float = 5.0, max_retries: int = 0) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="test tool",
        input_schema={"type": "object"},
        run=run,
        risk_tier=RiskTier.safe,
        timeout_s=timeout_s,
        max_retries=max_retries,
    )


@pytest.mark.asyncio
async def test_timeout_returns_error_and_does_not_hang():
    async def slow(args, ctx):
        await asyncio.sleep(30)

    spec = _spec("slow_tool", slow, timeout_s=0.05)
    with pytest.raises(ToolTimeoutError, match="timed out after"):
        await execute_tool_call(spec, {}, ToolContext(db=None))


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def flaky(args, ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    spec = _spec("flaky_tool", flaky, max_retries=2)
    result = await execute_tool_call(spec, {}, ToolContext(db=None))
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_exhaustion_returns_error_after_max_attempts():
    calls = {"n": 0}

    async def always_fail(args, ctx):
        calls["n"] += 1
        raise RuntimeError("boom")

    spec = _spec("failing_tool", always_fail, max_retries=2)
    with pytest.raises(RuntimeError, match="boom"):
        await execute_tool_call(spec, {}, ToolContext(db=None))
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_error_string_result_is_not_retried():
    calls = {"n": 0}

    async def intentional_error(args, ctx):
        calls["n"] += 1
        return "error: deliberate tool failure"

    spec = _spec("intentional_tool", intentional_error, max_retries=3)
    result = await execute_tool_call(spec, {}, ToolContext(db=None))
    assert result == "error: deliberate tool failure"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_zero_timeout_disables_deadline():
    async def quick(args, ctx):
        return "done"

    spec = _spec("no_deadline", quick, timeout_s=0)
    result = await execute_tool_call(spec, {}, ToolContext(db=None))
    assert result == "done"


@pytest.mark.asyncio
async def test_invalid_arguments_still_short_circuits_before_run():
    calls = {"n": 0}

    async def never(args, ctx):
        calls["n"] += 1
        return "should not happen"

    spec = _spec("validated_tool", never, max_retries=2)
    spec.input_schema = {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}
    result = await execute_tool_call(spec, {}, ToolContext(db=None))
    assert result.startswith("error: invalid arguments")
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_cancellation_propagates_through_retry_loop():
    async def cancellable(args, ctx):
        await asyncio.sleep(30)

    spec = _spec("cancelled_tool", cancellable, timeout_s=5.0)
    task = asyncio.create_task(execute_tool_call(spec, {}, ToolContext(db=None)))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_timeout_error_is_not_retried():
    calls = {"n": 0}

    async def slow(args, ctx):
        calls["n"] += 1
        await asyncio.sleep(30)

    spec = _spec("slow_no_retry", slow, timeout_s=0.05, max_retries=3)
    with pytest.raises(ToolTimeoutError, match="timed out after"):
        await execute_tool_call(spec, {}, ToolContext(db=None))
    assert calls["n"] == 1
