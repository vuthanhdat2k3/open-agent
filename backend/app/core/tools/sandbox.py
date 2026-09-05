from __future__ import annotations

import asyncio
import io
import os
import shlex
import tarfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.observability.metrics import sandbox_executions_total
from app.core.tools.filesystem import safe_resolve
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.services.workspace_service import (
    finish_execution_record,
    start_execution_record,
    upsert_workspace_artifact,
)

settings = get_settings()

MAX_SANDBOX_OUTPUT = 50_000
MAX_WORKSPACE_ARCHIVE_BYTES = 10 * 1024 * 1024
SKIP_WORKSPACE_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".codegraph", ".omo"}

_LANG_IMAGES = {
    "python": (settings.sandbox_docker_image_python, "python"),
    "bash": (settings.sandbox_docker_image_bash, "bash"),
    "node": (settings.sandbox_docker_image_node, "node"),
    "javascript": (settings.sandbox_docker_image_node, "node"),
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


async def _kill_container(name: str) -> None:
    """Force-remove a sandbox container by name.

    Killing the ``docker run`` CLI client alone (``proc.kill()``) leaves the
    detached container running in the daemon forever — ``--rm`` only fires
    when the container's main process actually exits, and a script that
    hangs (infinite loop / blocking stdin) never does. Removing it by name
    from the daemon side guarantees the orphan is cleaned up.
    """
    for args in (("docker", "kill", name), ("docker", "rm", "-f", name)):
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception:  # noqa: BLE001 - best effort cleanup
            continue


def build_docker_args(
    language: str,
    filename: str | None = None,
    *,
    stdin_mode: str = "code",
    name: str | None = None,
    rm: bool = True,
) -> list[str]:
    image, cmd = _LANG_IMAGES[language]
    fname = filename or f"script.{'py' if language == 'python' else 'sh'}"
    fname = os.path.basename(str(fname)) or "script.py"
    container_path = f"/work/{fname}"

    network = "none" if not settings.sandbox_allow_network else "bridge"
    safe_path = shlex.quote(container_path)
    if stdin_mode == "archive":
        runner = f"tar -xzf - -C /work && {cmd} {safe_path}"
    else:
        runner = f"cat > {safe_path} && {cmd} {safe_path}"
    args = [
        "docker",
        "run",
        "-i",
    ]
    if rm:
        args.append("--rm")
    if name:
        args += ["--name", name]
    args += [
        "--network",
        network,
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
    ]
    if rm:
        args += [
            "--read-only",
            "--tmpfs",
            "/work:rw,size=64m",
        ]
    args += [
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
    return args


def build_workspace_archive(workspace_dir: str, filename: str, code: str) -> bytes:
    """Package workspace files plus the requested script for stdin into Docker."""
    fname = os.path.basename(str(filename)) or "script.py"
    base = Path(workspace_dir).resolve()
    buf = io.BytesIO()
    total_size = 0

    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        if base.exists():
            for path in base.rglob("*"):
                rel = path.relative_to(base)
                if any(part in SKIP_WORKSPACE_DIRS for part in rel.parts):
                    continue
                if path.is_dir():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                total_size += stat.st_size
                if total_size > MAX_WORKSPACE_ARCHIVE_BYTES:
                    raise ValueError("workspace archive exceeds 10MB")
                archive.add(path, arcname=str(rel))

        data = str(code).encode("utf-8")
        info = tarfile.TarInfo(fname)
        info.size = len(data)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(data))

    return buf.getvalue()


async def sync_sandbox_artifacts(
    cname: str,
    workspace_dir: str,
    *,
    script_filename: str | None = None,
    ctx: ToolContext | None = None,
    source_tool: str = "run_code",
) -> list[str]:
    """Inspect newly created or modified files in the sandbox container and sync back to workspace_dir."""
    if not _docker_available():
        return []

    script_name = os.path.basename(str(script_filename)) if script_filename else None

    # 1. Run docker diff to detect added (A) or changed (C) files in /work
    try:
        diff_proc = await asyncio.create_subprocess_exec(
            "docker",
            "diff",
            cname,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        diff_out, _ = await diff_proc.communicate()
    except Exception:
        return []

    if diff_proc.returncode != 0 or not diff_out:
        return []

    changed_paths: set[str] = set()
    for line in diff_out.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not (line.startswith("A ") or line.startswith("C ")):
            continue
        if "/work/" not in line:
            continue
        rel_path = line.split("/work/", 1)[1].strip()
        if not rel_path or rel_path == ".":
            continue
        if script_name and rel_path == script_name:
            continue
        if any(skip in rel_path for skip in SKIP_WORKSPACE_DIRS):
            continue
        if rel_path.endswith((".pyc", ".pyo", ".pyd")):
            continue
        changed_paths.add(rel_path)

    if not changed_paths:
        return []

    # 2. Extract files using docker cp tar stream
    try:
        cp_proc = await asyncio.create_subprocess_exec(
            "docker",
            "cp",
            f"{cname}:/work/.",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        tar_bytes, _ = await cp_proc.communicate()
    except Exception:
        return []

    if cp_proc.returncode != 0 or not tar_bytes:
        return []

    synced_files: list[str] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
            for member in tar.getmembers():
                clean_name = member.name.lstrip("./")
                if clean_name not in changed_paths or member.isdir():
                    continue
                # Maximum 50MB per artifact to prevent filling host disk
                if member.size > 50 * 1024 * 1024:
                    continue

                target = safe_resolve(workspace_dir, clean_name)
                if target is None:
                    continue

                f = tar.extractfile(member)
                if f is None:
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read())
                synced_files.append(clean_name)

                if ctx and ctx.db and ctx.org_id:
                    try:
                        await upsert_workspace_artifact(
                            ctx.db,
                            org_id=ctx.org_id,
                            path=target,
                            workspace_dir=workspace_dir,
                            source_tool=source_tool,
                            user_id=ctx.user_id,
                            agent_id=ctx.agent_id,
                            session_id=ctx.session_id,
                            task_id=ctx.current_task_id,
                            root_run_id=ctx.root_run_id,
                        )
                    except Exception:
                        pass
    except Exception:
        pass

    return synced_files


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
    cname = f"oa-sandbox-{uuid.uuid4().hex[:12]}"
    docker_args = build_docker_args(lang, filename, name=cname)

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
            await _kill_container(cname)
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            sandbox_executions_total.labels("timeout").inc()
            yield {"event": "error", "data": {"message": f"Sandbox timed out after {tout}s"}}
            return

        if truncated:
            await _kill_container(cname)
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
        await _kill_container(cname)
        sandbox_executions_total.labels("docker_missing").inc()
        yield {"event": "error", "data": {"message": "Docker CLI not found on the backend host"}}
    except Exception as e:  # noqa: BLE001
        await _kill_container(cname)
        sandbox_executions_total.labels("error").inc()
        yield {"event": "error", "data": {"message": f"Error executing sandbox: {e}"}}


async def _run_code(args: dict[str, Any], ctx: ToolContext) -> str:
    if not settings.sandbox_enabled:
        sandbox_executions_total.labels("disabled").inc()
        return "error: sandbox execution is disabled"

    language = (args.get("language") or "python").lower()
    code = args.get("code")
    if code is None:
        code = args.get("content", "")
    execution = await start_execution_record(
        ctx.db,
        org_id=ctx.org_id,
        source="run_code",
        language=language,
        command=str(code)[:4000],
        user_id=ctx.user_id,
        agent_id=ctx.agent_id,
        session_id=ctx.session_id,
        task_id=ctx.current_task_id,
        root_run_id=ctx.root_run_id,
    )
    if language not in _LANG_IMAGES:
        msg = f"error: unsupported language '{language}' (use python or bash)"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg
    if not code:
        msg = "error: missing 'code'"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg

    try:
        timeout = float(args.get("timeout", settings.sandbox_default_timeout))
    except (TypeError, ValueError):
        timeout = settings.sandbox_default_timeout

    if not _docker_available():
        sandbox_executions_total.labels("docker_unavailable").inc()
        msg = (
            "error: docker unavailable — sandbox execution requires a running "
            "Docker daemon reachable from the backend host"
        )
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg

    filename = args.get("filename") or f"script.{'py' if language == 'python' else 'sh'}"
    try:
        archive = build_workspace_archive(ctx.workspace_dir, filename, str(code))
    except ValueError as e:
        msg = f"error: {e}"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg

    cname = f"oa-sandbox-{uuid.uuid4().hex[:12]}"
    docker_args = build_docker_args(language, filename, stdin_mode="archive", name=cname, rm=False)

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if proc.stdin:
            proc.stdin.write(archive)
            await proc.stdin.drain()
            proc.stdin.close()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        timed_out = False
        truncated = False
        total_chars = 0
        lines: list[str] = []
        if proc.stdout:
            while True:
                remaining = deadline - loop.time()
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
                line = line_bytes.decode("utf-8", errors="replace")
                total_chars += len(line)
                if total_chars > MAX_SANDBOX_OUTPUT:
                    truncated = True
                    overflow = total_chars - MAX_SANDBOX_OUTPUT
                    if overflow < len(line):
                        line = line[:-overflow] + "\n...[truncated output limit reached]"
                    else:
                        line = "\n...[truncated output limit reached]"
                    lines.append(line)
                    if ctx.emit:
                        await ctx.emit({"kind": "stdout", "line": line})
                    break
                lines.append(line)
                if ctx.emit:
                    await ctx.emit({"kind": "stdout", "line": line})

        if timed_out:
            try:
                proc.kill()
                await proc.wait()
            except Exception:  # noqa: BLE001
                pass
            sandbox_executions_total.labels("timeout").inc()
            msg = f"error: sandbox timed out after {timeout}s [exit code: -1]"
            await finish_execution_record(
                ctx.db,
                execution,
                status="timed_out",
                output=msg,
                error=msg,
                exit_code=-1,
            )
            return msg

        if truncated:
            try:
                proc.kill()
                await proc.wait()
            except Exception:  # noqa: BLE001
                pass
            text = "".join(lines) + "\n[exit code: -1]"
            sandbox_executions_total.labels("error").inc()
            await finish_execution_record(
                ctx.db,
                execution,
                status="failed",
                output=text,
                exit_code=-1,
            )
            return text

        await proc.wait()
        text = "".join(lines)
        if len(text) > MAX_SANDBOX_OUTPUT:
            text = text[:MAX_SANDBOX_OUTPUT] + "\n...[truncated]"
        text += f"\n[exit code: {proc.returncode}]"

        if proc.returncode == 0:
            synced = await sync_sandbox_artifacts(
                cname,
                ctx.workspace_dir,
                script_filename=filename,
                ctx=ctx,
                source_tool="run_code",
            )
            if synced:
                text += f"\n[artifacts synced to workspace: {', '.join(synced)}]"

        sandbox_executions_total.labels("ok" if proc.returncode == 0 else "error").inc()
        await finish_execution_record(
            ctx.db,
            execution,
            status="succeeded" if proc.returncode == 0 else "failed",
            output=text,
            exit_code=proc.returncode,
        )
        return text
    except FileNotFoundError:
        sandbox_executions_total.labels("docker_missing").inc()
        msg = "error: docker CLI not found on the backend host"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=msg)
        return msg
    except Exception as e:  # noqa: BLE001
        sandbox_executions_total.labels("error").inc()
        msg = f"error executing sandbox: {e}"
        await finish_execution_record(ctx.db, execution, status="failed", output=msg, error=str(e))
        return msg
    finally:
        await _kill_container(cname)

register(
    ToolSpec(
        name="run_code",
        description=(
            "Execute Python, bash, or JavaScript/Node.js inside an isolated Docker container and return "
            "its combined output plus exit code. Code cannot access the host or "
            "network (unless enabled). Provide 'language' (python|bash|javascript) and 'code'. "
            "Optional 'filename', 'timeout' (seconds). Use language='python' for "
            "Python code, language='javascript' for Node.js. The bash image is minimal and does not include python, "
            "pip, npm, apt-get, or build tools.\n\n"
            "NOTE FOR GRAPHICS & DRAWINGS: The sandbox runs in headless mode (no GUI/turtle/X11). "
            "To draw or display visual graphics (flowers, charts, diagrams) directly in the Chat UI, "
            "do NOT use matplotlib/turtle/tkinter or try to install GUI packages. "
            "Instead, print raw SVG markup (e.g. print('<svg ...>...</svg>')) "
            "or HTML directly to stdout. The OpenAgent Chat UI will automatically render the live interactive "
            "graphic preview directly inside the conversation thread for the user!"
        ),
        risk_tier=RiskTier.execute,
        input_schema={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "python, bash, or javascript (Node.js)",
                    "enum": ["python", "bash", "javascript", "node"],
                },
                "code": {
                    "type": "string",
                    "description": "Source code to execute",
                },
                "content": {
                    "type": "string",
                    "description": "Alias for 'code' for compatibility with code-writing prompts",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional filename (default script.py/script.sh/script.js)",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default 30)",
                },
            },
            "required": ["language"],
        },
        run=_run_code,
    )
)
