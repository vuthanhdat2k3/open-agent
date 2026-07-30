from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import AsyncIterator
from typing import Any

from app.config import get_settings
from app.core.observability.metrics import sandbox_executions_total
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec

settings = get_settings()

MAX_SANDBOX_OUTPUT = 50_000

_LANG_IMAGES = {
    "python": (settings.sandbox_docker_image_python, "python"),
    "bash": (settings.sandbox_docker_image_bash, "bash"),
}

_DOCKER_OK: bool | None = None


def _docker_available() -> bool:
    global _DOCKER_OK
    if _DOCKER_OK is not None:
        return _DOCKER_OK
    _DOCKER_OK = os.path.exists("/var/run/docker.sock") or _docker_cli_present()
    return _DOCKER_OK


def _docker_cli_present() -> bool:
    from shutil import which

    return which("docker") is not None


def build_docker_args(language: str, filename: str | None = None) -> list[str]:
    image, cmd = _LANG_IMAGES[language]
    fname = filename or f"script.{'py' if language == 'python' else 'sh'}"
    fname = os.path.basename(str(fname)) or "script.py"
    container_path = f"/work/{fname}"

    network = "none" if not settings.sandbox_allow_network else "bridge"
    safe_path = shlex.quote(container_path)
    runner = f"cat > {safe_path} && {cmd} {safe_path}"
    return [
        "docker",
        "run",
        "-i",
        "--rm",
        "--network",
        network,
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--read-only",
        "--tmpfs",
        "/work:rw,size=64m",
        "--memory",
        settings.sandbox_memory,
        "--cpus",
        str(settings.sandbox_cpus),
        "-w",
        "/work",
        image,
        "sh",
        "-c",
        runner,
    ]


async def stream_sandbox_execution(
    language: str,
    code: str,
    filename: str | None = None,
    timeout: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if not settings.sandbox_enabled:
        sandbox_executions_total.labels("disabled").inc()
        yield {"event": "error", "data": {"message": "Sandbox execution is disabled"}}
        return

    lang = language.lower()
    if lang not in _LANG_IMAGES:
        sandbox_executions_total.labels("error").inc()
        yield {"event": "error", "data": {"message": f"Unsupported language '{language}' (use python or bash)"}}
        return

    if not code:
        sandbox_executions_total.labels("error").inc()
        yield {"event": "error", "data": {"message": "Missing code to execute"}}
        return

    if not _docker_available():
        sandbox_executions_total.labels("docker_unavailable").inc()
        yield {
            "event": "error",
            "data": {
                "message": "Docker unavailable — sandbox execution requires a running Docker daemon reachable from the backend host"
            },
        }
        return

    tout = timeout if timeout is not None else float(settings.sandbox_default_timeout)
    docker_args = build_docker_args(lang, filename)

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        if proc.stdin:
            proc.stdin.write(str(code).encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

        loop = asyncio.get_running_loop()
        start_time = loop.time()
        timed_out = False
        truncated = False
        total_chars = 0

        if proc.stdout:
            while True:
                elapsed = loop.time() - start_time
                remaining = tout - elapsed
                if remaining <= 0:
                    timed_out = True
                    break

                try:
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=max(0.1, remaining),
                    )
                except TimeoutError:
                    timed_out = True
                    break

                if not line_bytes:
                    break

                line_str = line_bytes.decode("utf-8", errors="replace")
                total_chars += len(line_str)

                if total_chars > MAX_SANDBOX_OUTPUT:
                    truncated = True
                    overflow = total_chars - MAX_SANDBOX_OUTPUT
                    if overflow < len(line_str):
                        line_str = line_str[:-overflow] + "\n...[truncated output limit reached]"
                        yield {"event": "stdout", "data": {"line": line_str}}
                    else:
                        yield {"event": "stdout", "data": {"line": "\n...[truncated output limit reached]"}}
                    break

                yield {"event": "stdout", "data": {"line": line_str}}

        if timed_out:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            sandbox_executions_total.labels("timeout").inc()
            yield {"event": "error", "data": {"message": f"Sandbox timed out after {tout}s"}}
            return

        if truncated:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            sandbox_executions_total.labels("error").inc()
            yield {"event": "exit", "data": {"code": -1}}
            return

        await proc.wait()
        sandbox_executions_total.labels("ok" if proc.returncode == 0 else "error").inc()
        yield {"event": "exit", "data": {"code": proc.returncode}}

    except FileNotFoundError:
        sandbox_executions_total.labels("docker_missing").inc()
        yield {"event": "error", "data": {"message": "Docker CLI not found on the backend host"}}
    except Exception as e:  # noqa: BLE001
        sandbox_executions_total.labels("error").inc()
        yield {"event": "error", "data": {"message": f"Error executing sandbox: {e}"}}


async def _run_code(args: dict[str, Any], ctx: ToolContext) -> str:
    if not settings.sandbox_enabled:
        sandbox_executions_total.labels("disabled").inc()
        return "error: sandbox execution is disabled"

    language = (args.get("language") or "python").lower()
    code = args.get("code", "")
    if language not in _LANG_IMAGES:
        return f"error: unsupported language '{language}' (use python or bash)"
    if not code:
        return "error: missing 'code'"

    try:
        timeout = float(args.get("timeout", settings.sandbox_default_timeout))
    except (TypeError, ValueError):
        timeout = settings.sandbox_default_timeout

    if not _docker_available():
        sandbox_executions_total.labels("docker_unavailable").inc()
        return (
            "error: docker unavailable — sandbox execution requires a running "
            "Docker daemon reachable from the backend host"
        )

    filename = args.get("filename") or f"script.{'py' if language == 'python' else 'sh'}"
    docker_args = build_docker_args(language, filename)

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(str(code).encode("utf-8")),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            sandbox_executions_total.labels("timeout").inc()
            return f"error: sandbox timed out after {timeout}s [exit code: -1]"
    except FileNotFoundError:
        sandbox_executions_total.labels("docker_missing").inc()
        return "error: docker CLI not found on the backend host"
    except Exception as e:  # noqa: BLE001
        sandbox_executions_total.labels("error").inc()
        return f"error executing sandbox: {e}"

    text = out.decode("utf-8", errors="replace") if out else ""
    if len(text) > MAX_SANDBOX_OUTPUT:
        text = text[:MAX_SANDBOX_OUTPUT] + "\n...[truncated]"
    text += f"\n[exit code: {proc.returncode}]"
    sandbox_executions_total.labels("ok" if proc.returncode == 0 else "error").inc()
    return text


register(
    ToolSpec(
        name="run_code",
        description=(
            "Execute Python or bash inside an isolated Docker container and return "
            "its combined output plus exit code. Code cannot access the host or "
            "network (unless enabled). Provide 'language' (python|bash) and 'code'. "
            "Optional 'filename', 'timeout' (seconds).\n\n"
            "NOTE FOR GRAPHICS & DRAWINGS: The sandbox runs in headless mode (no GUI/turtle/X11). "
            "To draw or display visual graphics (flowers, charts, diagrams) directly in the Chat UI, "
            "do NOT use turtle/tkinter. Instead, print raw SVG markup (e.g. print('<svg ...>...</svg>')) "
            "or HTML directly to stdout. The OpenAgent Chat UI will automatically render the live interactive "
            "graphic preview directly inside the conversation thread for the user!"
        ),
        risk_tier=RiskTier.execute,
        input_schema={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "python or bash",
                    "enum": ["python", "bash"],
                },
                "code": {
                    "type": "string",
                    "description": "Source code to execute",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional filename (default script.py/script.sh)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default 30)",
                },
            },
            "required": ["language", "code"],
        },
        run=_run_code,
    )
)
