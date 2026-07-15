from __future__ import annotations

import asyncio
from typing import Any

from app.core.tools.paths import safe_resolve
from app.core.tools.registry import register
from app.core.tools.types import ToolContext, ToolSpec

MAX_SHELL_OUTPUT = 50_000
DEFAULT_TIMEOUT = 30.0


async def _run_shell(args: dict[str, Any], ctx: ToolContext) -> str:
    cmd = args.get("cmd", "")
    if not cmd:
        return "error: missing 'cmd'"

    cwd_arg = args.get("cwd")
    if cwd_arg:
        cwd = safe_resolve(ctx.workspace_dir, cwd_arg)
        if cwd is None or not cwd.is_dir():
            return "error: cwd escapes workspace directory or is not a directory"
        cwd_str = str(cwd)
    else:
        cwd_str = ctx.workspace_dir

    try:
        timeout = float(args.get("timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=cwd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return f"error: command timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return f"error executing command: {e}"

    text = out.decode("utf-8", errors="replace") if out else ""
    if len(text) > MAX_SHELL_OUTPUT:
        text = text[:MAX_SHELL_OUTPUT] + "\n...[truncated]"
    text += f"\n[exit code: {proc.returncode}]"
    return text


register(
    ToolSpec(
        name="run_shell",
        description=(
            "Execute a shell command in the workspace and return its combined "
            "output plus exit code. DANGEROUS: only grant to trusted agents. "
            "Optional 'cwd' (relative, within workspace) and 'timeout' (seconds)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "cwd": {
                    "type": "string",
                    "description": "Relative working directory (optional)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default 30)",
                },
            },
            "required": ["cmd"],
        },
        run=_run_shell,
    )
)
