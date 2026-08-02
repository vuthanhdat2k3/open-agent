from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from app.core.tools import sandbox
from app.core.tools.paths import safe_resolve
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.services.workspace_service import finish_execution_record, start_execution_record

MAX_SHELL_OUTPUT = 50_000
DEFAULT_TIMEOUT = 30.0


async def _run_shell(args: dict[str, Any], ctx: ToolContext) -> str:
    """Run ``cmd`` inside the same hardened Docker sandbox as run_code (never
    on the backend host) — the workspace is archived in, cmd runs as a bash
    script, and results come back over stdout, matching sandbox._run_code's
    stdin_mode="archive" contract.
    """
    cmd = args.get("cmd", "")
    if not cmd:
        return "error: missing 'cmd'"
    if not sandbox.settings.sandbox_enabled:
        return "error: sandbox execution is disabled"

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
    rel_cwd = None
    if cwd_arg:
        cwd = safe_resolve(ctx.workspace_dir, cwd_arg)
        if cwd is None or not cwd.is_dir():
            msg = "error: cwd escapes workspace directory or is not a directory"
            await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
            return msg
        rel_cwd = os.path.relpath(str(cwd), os.path.abspath(ctx.workspace_dir))

    try:
        timeout = float(args.get("timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    if not sandbox._docker_available():
        msg = (
            "error: docker unavailable — sandbox execution requires a running "
            "Docker daemon reachable from the backend host"
        )
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg

    script = f"cd {shlex.quote(rel_cwd)} && {cmd}" if rel_cwd and rel_cwd != "." else cmd
    try:
        archive = sandbox.build_workspace_archive(ctx.workspace_dir, "run_shell.sh", script)
    except ValueError as e:
        msg = f"error: {e}"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg

    docker_args = sandbox.build_docker_args("bash", "run_shell.sh", stdin_mode="archive")

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(archive), timeout=timeout)
    except TimeoutError:
        msg = f"error: command timed out after {timeout}s"
        await finish_execution_record(ctx.db, execution, status="timed_out", output=msg, error=msg)
        return msg
    except FileNotFoundError:
        msg = "error: docker CLI not found on the backend host"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
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
