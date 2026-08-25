import asyncio
from typing import Any

from jsonschema import ValidationError, validate

from app.core.tools.types import ToolContext, ToolSpec

# name -> spec. Populated by app.core.tools.builtins on import.
BUILTIN_TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    BUILTIN_TOOLS[spec.name] = spec


def get_tool(name: str) -> ToolSpec | None:
    return BUILTIN_TOOLS.get(name)


def list_tools() -> list[ToolSpec]:
    return list(BUILTIN_TOOLS.values())


class ToolTimeoutError(Exception):
    """Raised when a tool exceeds its ``timeout_s`` deadline.

    Timeouts are never retried: the tool already had its full budget of wall
    time, and re-running it would likely hang again.
    """

    pass


async def _run_with_timeout(spec: ToolSpec, args: dict[str, Any], ctx: ToolContext) -> str:
    if spec.timeout_s and spec.timeout_s > 0:
        try:
            return await asyncio.wait_for(spec.run(args, ctx), timeout=spec.timeout_s)
        except (asyncio.TimeoutError, TimeoutError):  # noqa: UP041 -- alias only on py311+; py310 raises the asyncio class
            # asyncio.TimeoutError is an alias of the builtin only on
            # Python 3.11+; 3.10 still raises the asyncio-specific class.
            raise ToolTimeoutError(
                f"tool '{spec.name}' timed out after {spec.timeout_s:g}s"
            ) from None
    return await spec.run(args, ctx)


async def execute_tool_call(spec: ToolSpec, args: dict[str, Any], ctx: ToolContext) -> str:
    """Validate args and run the tool, enforcing ``timeout_s`` / ``max_retries``.

    Invalid arguments keep the historical error-string contract (the agent
    loop feeds it back to the model). Execution errors raise after exhausting
    attempts - callers own their retry accounting.
    """
    try:
        validate(instance=args, schema=spec.input_schema)
    except ValidationError as exc:
        path = ".".join(str(p) for p in exc.path)
        location = f" at {path}" if path else ""
        return f"error: invalid arguments{location}: {exc.message}"
    attempts = 1 + max(0, spec.max_retries)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await _run_with_timeout(spec, args, ctx)
        except asyncio.CancelledError:
            raise
        except ToolTimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
    raise last_error
