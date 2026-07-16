from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.tools.registry import register
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


async def _run_code(args: dict[str, Any], ctx: ToolContext) -> str:
    if not settings.sandbox_enabled:
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
        return (
            "error: docker unavailable — sandbox execution requires a running "
            "Docker daemon reachable from the backend host"
        )

    image, cmd = _LANG_IMAGES[language]
    filename = args.get("filename") or f"script.{ 'py' if language == 'python' else 'sh' }"

    work_root = Path(ctx.workspace_dir).resolve() / ".sandbox"
    work_root.mkdir(parents=True, exist_ok=True)
    run_dir = work_root / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / filename
    target.write_text(str(code), encoding="utf-8")

    network = "none" if not settings.sandbox_allow_network else "bridge"
    docker_args = [
        "docker", "run", "--rm",
        "--network", network,
        "--memory", settings.sandbox_memory,
        "--cpus", str(settings.sandbox_cpus),
        "-v", f"{run_dir}:/work:rw",
        "-w", "/work",
        image, cmd, filename,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"error: sandbox timed out after {timeout}s [exit code: -1]"
    except FileNotFoundError:
        return "error: docker CLI not found on the backend host"
    except Exception as e:  # noqa: BLE001
        return f"error executing sandbox: {e}"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

    text = out.decode("utf-8", errors="replace") if out else ""
    if len(text) > MAX_SANDBOX_OUTPUT:
        text = text[:MAX_SANDBOX_OUTPUT] + "\n...[truncated]"
    text += f"\n[exit code: {proc.returncode}]"
    return text


register(
    ToolSpec(
        name="run_code",
        description=(
            "Execute Python or bash inside an isolated Docker container and return "
            "its combined output plus exit code. Code cannot access the host or "
            "network (unless enabled). Provide 'language' (python|bash) and 'code'. "
            "Optional 'filename', 'timeout' (seconds)."
        ),
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
