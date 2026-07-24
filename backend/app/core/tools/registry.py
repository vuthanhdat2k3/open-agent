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


async def execute_tool_call(spec: ToolSpec, args: dict[str, Any], ctx: ToolContext) -> str:
    try:
        validate(instance=args, schema=spec.input_schema)
    except ValidationError as exc:
        path = ".".join(str(p) for p in exc.path)
        location = f" at {path}" if path else ""
        return f"error: invalid arguments{location}: {exc.message}"
    return await spec.run(args, ctx)
