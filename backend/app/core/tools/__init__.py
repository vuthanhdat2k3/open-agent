# Importing this package registers all builtin tools as a side effect.
# Any `from app.core.tools.registry import ...` transitively runs this and
# populates BUILTIN_TOOLS at startup.
from app.core.tools import (
    builtins,  # noqa: F401
    sandbox,  # noqa: F401
)
