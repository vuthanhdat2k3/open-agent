from __future__ import annotations

import asyncio
from typing import Any

from app.core.tools.paths import safe_resolve
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.services.workspace_service import finish_execution_record, start_execution_record

MAX_SHELL_OUTPUT = 50_000
DEFAULT_TIMEOUT = 30.0


async def _run_shell(args: dict[str, Any], ctx: ToolContext) -> str:
    cmd = args.get("cmd", "")
    if not cmd:
        return "error: missing 'cmd'"
    execution = await start_execution_record(
        ctx.db,
        org_id=ctx.org_id,
        source="run_shell",
        language="shell",
        command=cmd,
        user_id=ctx.user_id,
        agent_id=ctx.agent_id,
        session_id=ctx.session_id,
        task_id=ctx.current_task_id,
        root_run_id=ctx.root_run_id,
    )

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
    except TimeoutError:
        msg = f"error: command timed out after {timeout}s"
        await finish_execution_record(ctx.db, execution, status="timed_out", output=msg, error=msg)
        return msg
    except Exception as e:  # noqa: BLE001
        msg = f"error executing command: {e}"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=str(e))
        return msg

    text = out.decode("utf-8", errors="replace") if out else ""
    if len(text) > MAX_SHELL_OUTPUT:
        text = text[:MAX_SHELL_OUTPUT] + "\n...[truncated]"
    text += f"\n[exit code: {proc.returncode}]"
    await finish_execution_record(
        ctx.db,
        execution,
        status="succeeded" if proc.returncode == 0 else "failed",
        output=text,
        exit_code=proc.returncode,
    )
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
        risk_tier=RiskTier.dangerous,
        requires_approval=True,
    )
)
