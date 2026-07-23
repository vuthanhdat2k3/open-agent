from app.core.tools.types import ToolSpec

# name -> spec. Populated by app.core.tools.builtins on import.
BUILTIN_TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    BUILTIN_TOOLS[spec.name] = spec


def get_tool(name: str) -> ToolSpec | None:
    return BUILTIN_TOOLS.get(name)


def list_tools() -> list[ToolSpec]:
    return list(BUILTIN_TOOLS.values())
