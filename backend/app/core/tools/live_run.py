from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.tools.sandbox import (
    _kill_container,
    build_docker_args,
    build_workspace_archive,
)
from app.models.workspace import SandboxExecution
from app.services.workspace_service import (
    WorkspaceService,
    finish_execution_record,
    start_execution_record,
)

MAX_LIVE_RUN_OUTPUT = 50_000


class RunAlreadyActive(Exception):
    """Raised when an org already has a live run in the registry."""


@dataclass
class LiveRun:
    org_id: str
    execution_id: str
    artifact_id: str
    language: str
    container_name: str
    queue: asyncio.Queue  # holds {"event": ..., "data": {...}} dicts
    reader_task: asyncio.Task
    started_monotonic: float
    max_seconds: float
    status: str
    session_factory: async_sessionmaker[AsyncSession] | None = None
    _stop_timer: asyncio.Task | None = field(default=None, init=False, repr=False)

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - (time.monotonic() - self.started_monotonic))


# Keyed by org_id. Guarded by _lock for start/stop.
_REGISTRY: dict[str, LiveRun] = {}
_lock = asyncio.Lock()


async def _make_factory(db: AsyncSession) -> async_sessionmaker[AsyncSession] | None:
    """Derive a session factory bound to the same engine as the request session.

    Background reader/timer tasks finalize execution records after the
    request-scoped session is closed, so they need their own factory resolving
    to the same engine (critical for the in-memory sqlite used in tests).
    """
    try:
        engine = db.bind
        return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    except Exception:  # noqa: BLE001
        return None


async def _spawn_process(docker_args: list[str], archive: bytes) -> Any:
    """SEAM: spawn the sandbox container and feed the workspace archive to stdin.

    Tests monkeypatch this to return a FakeProc, so CI never needs a Docker
    daemon. Mirrors ``_run_code`` in sandbox.py.
    """
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
    return proc


async def _reader(org_id: str, live_run: LiveRun, proc: Any) -> None:
    """Background task: stream stdout lines into the run's queue, then finalize."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    collected: list[str] = []
    total_chars = 0
    truncated = False
    try:
        stdout = getattr(proc, "stdout", None)
        if stdout is not None:
            while True:
                line_bytes = await stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                total_chars += len(line)
                if total_chars > MAX_LIVE_RUN_OUTPUT:
                    truncated = True
                    overflow = total_chars - MAX_LIVE_RUN_OUTPUT
                    if overflow < len(line):
                        line = line[:-overflow] + "\n...[truncated output limit reached]"
                    else:
                        line = "\n...[truncated output limit reached]"
                    await live_run.queue.put({"event": "stdout", "data": {"line": line}})
                    collected.append(line)
                    break
                collected.append(line)
                await live_run.queue.put({"event": "stdout", "data": {"line": line}})

        rc = await proc.wait()
        if truncated:
            rc = -1

        # Natural EOF (not user/timeout): finalize succeeds/fails and signal exit.
        factory = live_run.session_factory
        if factory is not None:
            async with factory() as s:
                record = await s.get(SandboxExecution, live_run.execution_id)
                text = "".join(collected)
                if truncated:
                    text += "\n[exit code: -1]"
                else:
                    text += f"\n[exit code: {rc}]"
                await finish_execution_record(
                    s,
                    record,
                    status="succeeded" if rc == 0 else "failed",
                    output=text,
                    exit_code=rc,
                )

        await live_run.queue.put({"event": "exit", "data": {"code": rc}})

        # The run naturally finished; remove from registry so the org can start
        # a new one. A subsequent stream serves the record from the DB instead.
        async with _lock:
            if _REGISTRY.get(org_id) is live_run:
                _REGISTRY.pop(org_id, None)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        # The stream is already detached from the request; leave the persisted
        # execution record as-is if finalization itself fails.
        return


async def _timeout_worker(org_id: str, live_run: LiveRun, max_seconds: float) -> None:
    try:
        await asyncio.sleep(max_seconds)
    except asyncio.CancelledError:
        return
    if _REGISTRY.get(org_id) is live_run:
        await stop_live_run(org_id, reason="timeout")


async def start_live_run(
    db: AsyncSession,
    *,
    org_id: str,
    user_id: str | None,
    artifact_id: str,
    workspace_dir: str,
    language: str,
) -> LiveRun:
    async with _lock:
        if org_id in _REGISTRY:
            raise RunAlreadyActive()

    svc = WorkspaceService(db)
    target = await svc.artifact_path(org_id, artifact_id)  # may raise ValueError/FileNotFoundError
    base = Path(workspace_dir).resolve()
    rel = target.relative_to(base).as_posix()
    code = target.read_text(encoding="utf-8", errors="replace")

    execution = await start_execution_record(
        db,
        org_id=org_id,
        source="workspace_run",
        language=language,
        command=rel,
        user_id=user_id,
    )
    if execution is None:
        raise RuntimeError("failed to start execution record")

    factory = await _make_factory(db)
    loop = asyncio.get_running_loop()
    cname = f"oa-run-{org_id[:8]}-{uuid.uuid4().hex[:8]}"
    docker_args = build_docker_args(language, filename=rel, stdin_mode="archive", name=cname)
    archive = build_workspace_archive(workspace_dir, filename=rel, code=code)

    proc = await _spawn_process(docker_args, archive)

    live_run = LiveRun(
        org_id=org_id,
        execution_id=execution.id,
        artifact_id=artifact_id,
        language=language,
        container_name=cname,
        queue=asyncio.Queue(),
        reader_task=None,  # type: ignore[assignment]  # assigned below
        started_monotonic=loop.time(),
        max_seconds=float(get_settings().sandbox_max_run_seconds),
        status="running",
        session_factory=factory,
    )
    live_run.reader_task = asyncio.create_task(_reader(org_id, live_run, proc))
    live_run._stop_timer = asyncio.create_task(_timeout_worker(org_id, live_run, live_run.max_seconds))

    async with _lock:
        _REGISTRY[org_id] = live_run
    return live_run


async def stop_live_run(org_id: str, *, reason: Literal["user", "timeout"] = "user") -> LiveRun | None:
    async with _lock:
        live_run = _REGISTRY.get(org_id)
    if live_run is None:
        return None

    await _kill_container(live_run.container_name)

    if live_run._stop_timer is not None:
        live_run._stop_timer.cancel()

    status = "stopped" if reason == "user" else "timed_out"
    await live_run.queue.put({"event": status, "data": {"reason": reason}})

    factory = live_run.session_factory
    if factory is not None:
        async with factory() as s:
            record = await s.get(SandboxExecution, live_run.execution_id)
            await finish_execution_record(
                s,
                record,
                status=status,
                error=None,
                exit_code=-1,
            )

    if live_run.reader_task is not None and not live_run.reader_task.done():
        live_run.reader_task.cancel()

    async with _lock:
        if _REGISTRY.get(org_id) is live_run:
            _REGISTRY.pop(org_id, None)
    return live_run


def get_active_run(org_id: str) -> LiveRun | None:
    return _REGISTRY.get(org_id)


async def stream_live_run(
    org_id: str, *, heartbeat: float = 15.0
) -> AsyncIterator[dict[str, Any]]:
    """Yield events from the active run's queue until a terminal event.

    Emits a ``heartbeat`` event periodically so long-lived streams survive
    idle timeouts in proxies/load-balancers.
    """
    live_run = _REGISTRY.get(org_id)
    if live_run is None:
        return
    while True:
        try:
            event = await asyncio.wait_for(live_run.queue.get(), timeout=heartbeat)
        except TimeoutError:
            yield {"event": "heartbeat", "data": {}}
            continue
        yield event
        if event.get("event") in ("exit", "stopped", "timeout"):
            return
