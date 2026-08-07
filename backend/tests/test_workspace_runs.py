from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.tools import live_run
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.workspace import SandboxExecution, WorkspaceArtifact
from app.services.workspace_service import upsert_workspace_artifact

# ---------------------------------------------------------------------------
# Planned API contract under test (red phase — routes + live_run do NOT exist):
#
#   POST /api/workspace/artifacts/{artifact_id}/run  -> 202
#       {execution_id, artifact_id, max_seconds}       (empty body; language
#       inferred from extension: .py -> python, .sh -> bash)
#   GET  /api/workspace/executions/active             -> ActiveRunOut | null
#   GET  /api/workspace/executions/{execution_id}/stream -> text/event-stream
#   POST /api/workspace/executions/{execution_id}/stop  -> {"ok": true}
#
# No real Docker is involved: app.core.tools.live_run._spawn_process is
# monkeypatched to an async fake returning FakeProc, and _kill_container is a
# no-op. CI never touches the Docker daemon.
# ---------------------------------------------------------------------------


class FakeProc:
    """Fake asyncio subprocess used by the live_run._spawn_process seam.

    ``stdout`` is a real ``asyncio.StreamReader`` pre-filled with scripted
    lines followed by EOF (unless ``eof=False``, which keeps the run active).
    """

    def __init__(
        self,
        lines: list[bytes] | None = None,
        returncode: int = 0,
        *,
        eof: bool = True,
    ) -> None:
        self.stdout = asyncio.StreamReader()
        for line in lines or []:
            self.stdout.feed_data(line)
        if eof:
            self.stdout.feed_eof()
        self._returncode = returncode
        self.killed = False

    @property
    def returncode(self) -> int:
        return self._returncode

    async def wait(self) -> int:
        return self._returncode

    async def kill(self) -> None:
        self.killed = True
        self._returncode = -1


def _patch_live_run(monkeypatch: pytest.MonkeyPatch, proc: FakeProc) -> dict[str, int]:
    """Install the live_run mock seam: fake spawn + no-op container kill.

    Returns a counter dict so tests can assert the kill path was exercised.
    """
    calls = {"spawn": 0, "kill_container": 0}

    async def fake_spawn(*_args, **_kwargs) -> FakeProc:
        calls["spawn"] += 1
        return proc

    async def fake_kill_container(_name: str) -> None:
        calls["kill_container"] += 1

    monkeypatch.setattr(live_run, "_spawn_process", fake_spawn)
    monkeypatch.setattr(live_run, "_kill_container", fake_kill_container)
    return calls


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        echo=False,
        connect_args={"timeout": 30},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _reset_live_run_registry():
    async def reset() -> None:
        runs = list(live_run._REGISTRY.values())
        for run in runs:
            if run._stop_timer is not None:
                run._stop_timer.cancel()
            if run.reader_task is not None and not run.reader_task.done():
                run.reader_task.cancel()
        for run in list(live_run._REGISTRY.values()):
            if run._stop_timer is not None:
                run._stop_timer.cancel()
            if run.reader_task is not None and not run.reader_task.done():
                run.reader_task.cancel()
        live_run._REGISTRY.clear()
        live_run._lock = asyncio.Lock()

    await reset()
    yield
    await reset()


@pytest.fixture
def client(async_session_factory):
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def workspace_env(client, async_session_factory, monkeypatch, tmp_path):
    """Authed owner + a seeded tmp workspace with main.py / run.sh / notes.txt.

    Also points ``settings.workspace_dir`` at the tmp dir and inserts
    WorkspaceArtifact rows through the same service function the app uses.
    """
    token = _register(client, "wr_owner@test.com", PASSWORD, "RunWorkspace")
    org_id = _get_org_id(client, token)
    monkeypatch.setattr(get_settings(), "workspace_dir", str(tmp_path))

    files = {
        "main.py": tmp_path / "main.py",
        "run.sh": tmp_path / "run.sh",
        "notes.txt": tmp_path / "notes.txt",
    }
    files["main.py"].write_text("print('hello from fake')\n", encoding="utf-8")
    files["run.sh"].write_text("echo hello from fake\n", encoding="utf-8")
    files["notes.txt"].write_text("plain notes\n", encoding="utf-8")

    async with async_session_factory() as db:
        for path in files.values():
            await upsert_workspace_artifact(
                db,
                org_id=org_id,
                path=path,
                workspace_dir=str(tmp_path),
                source_tool="test",
            )
        res = await db.execute(
            select(WorkspaceArtifact).where(WorkspaceArtifact.org_id == org_id)
        )
        ids = {row.path: row.id for row in res.scalars().all()}

    return SimpleNamespace(
        token=token,
        org_id=org_id,
        workspace_dir=str(tmp_path),
        ids=ids,
    )


# ---------------------------------------------------------------------------
# Auth helpers (mirrors test_authz.py)
# ---------------------------------------------------------------------------

PASSWORD = "Secret123!"


def _register(client: TestClient, email: str, password: str = PASSWORD, org_name: str | None = None) -> str:
    body = {"email": email, "password": password}
    if org_name:
        body["org_name"] = org_name
    resp = client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, f"register failed: {resp.text}"
    return resp.json()["access_token"]


def _get_org_id(client: TestClient, token: str) -> str:
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    return me.json()["memberships"][0]["org_id"]


def _add_member(client: TestClient, token: str, org_id: str, email: str, role: str) -> str:
    member_token = _register(client, email)
    resp = client.post(
        f"/api/orgs/{org_id}/members",
        json={"email": email, "role": role},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"add member failed: {resp.text}"
    return member_token


def _auth_headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Org-Id"] = org_id
    return headers


def _run_url(env: SimpleNamespace, key: str) -> str:
    return f"/api/workspace/artifacts/{env.ids[key]}/run"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_py_artifact_returns_202_and_execution_id(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(lines=[b"hello from fake\n"], returncode=0))

    resp = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["artifact_id"] == env.ids["main.py"]
    assert body["execution_id"]
    assert isinstance(body["max_seconds"], (int, float))


def test_run_unknown_artifact_404(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(lines=[b"x\n"]))

    resp = client.post(
        "/api/workspace/artifacts/does-not-exist/run",
        headers=_auth_headers(env.token, env.org_id),
    )

    assert resp.status_code == 404


def test_run_unsupported_extension_400(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(lines=[b"x\n"]))

    resp = client.post(_run_url(env, "notes.txt"), headers=_auth_headers(env.token, env.org_id))

    assert resp.status_code == 400


def test_run_while_active_409(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(eof=False))

    first = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))
    assert first.status_code == 202, first.text

    second = client.post(_run_url(env, "run.sh"), headers=_auth_headers(env.token, env.org_id))
    assert second.status_code == 409


def test_run_requires_files_read(client, workspace_env) -> None:
    env = workspace_env
    viewer_token = _add_member(client, env.token, env.org_id, "wr_viewer@test.com", "viewer")

    resp = client.post(
        _run_url(env, "main.py"),
        headers=_auth_headers(viewer_token, env.org_id),
    )

    assert resp.status_code == 403


def test_run_unauthenticated_401(client, workspace_env) -> None:
    env = workspace_env
    resp = client.post(_run_url(env, "main.py"))
    assert resp.status_code == 401


def test_active_run_returns_run_with_remaining_seconds(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(eof=False))

    run = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))
    assert run.status_code == 202, run.text
    execution_id = run.json()["execution_id"]

    active = client.get(
        "/api/workspace/executions/active",
        headers=_auth_headers(env.token, env.org_id),
    )

    assert active.status_code == 200, active.text
    body = active.json()
    assert body is not None
    assert body["id"] == execution_id
    assert body["status"] == "running"
    assert isinstance(body["remaining_seconds"], (int, float))
    assert body["remaining_seconds"] >= 0


def test_active_run_null_when_idle(client, workspace_env) -> None:
    env = workspace_env

    active = client.get(
        "/api/workspace/executions/active",
        headers=_auth_headers(env.token, env.org_id),
    )

    assert active.status_code == 200, active.text
    assert active.json() is None


def test_stream_emits_stdout_events_then_exit(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(lines=[b"hello from fake\n"], returncode=0))

    run = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))
    assert run.status_code == 202, run.text
    execution_id = run.json()["execution_id"]

    stream = client.get(
        f"/api/workspace/executions/{execution_id}/stream",
        headers=_auth_headers(env.token, env.org_id),
    )

    assert stream.status_code == 200, stream.text
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: stdout" in stream.text
    assert "hello from fake" in stream.text
    assert "event: exit" in stream.text


async def test_stop_marks_record_stopped_and_kills_container(
    client, workspace_env, async_session_factory, monkeypatch
) -> None:
    env = workspace_env
    calls = _patch_live_run(monkeypatch, FakeProc(eof=False))

    run = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))
    assert run.status_code == 202, run.text
    execution_id = run.json()["execution_id"]

    stop = client.post(
        f"/api/workspace/executions/{execution_id}/stop",
        headers=_auth_headers(env.token, env.org_id),
    )
    assert stop.status_code == 200, stop.text
    assert stop.json() == {"ok": True}

    async with async_session_factory() as db:
        record = await db.get(SandboxExecution, execution_id)
        assert record is not None
        assert record.status == "stopped"

    assert calls["kill_container"] >= 1


def test_stop_idle_404(client, workspace_env) -> None:
    env = workspace_env

    resp = client.post(
        "/api/workspace/executions/does-not-exist/stop",
        headers=_auth_headers(env.token, env.org_id),
    )

    assert resp.status_code == 404


async def test_timeout_autostops_with_timed_out(
    client, workspace_env, async_session_factory, monkeypatch
) -> None:
    env = workspace_env
    monkeypatch.setattr(get_settings(), "sandbox_max_run_seconds", 0.05)
    _patch_live_run(monkeypatch, FakeProc(eof=False))

    run = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))
    assert run.status_code == 202, run.text
    execution_id = run.json()["execution_id"]

    deadline = time.monotonic() + 5.0
    status: str | None = None
    while time.monotonic() < deadline:
        # TestClient owns the event loop where the detached timeout task runs.
        # Drive that loop while polling the isolated SQLite record.
        active = client.get(
            "/api/workspace/executions/active",
            headers=_auth_headers(env.token, env.org_id),
        )
        async with async_session_factory() as db:
            record = await db.get(SandboxExecution, execution_id)
            status = record.status if record else None
        if status == "timed_out" or active.json() is None:
            break
        await asyncio.sleep(0.05)

    assert status == "timed_out"


def test_org_isolation(client, workspace_env, monkeypatch) -> None:
    env = workspace_env
    _patch_live_run(monkeypatch, FakeProc(eof=False))

    run = client.post(_run_url(env, "main.py"), headers=_auth_headers(env.token, env.org_id))
    assert run.status_code == 202, run.text
    execution_id = run.json()["execution_id"]

    token_b = _register(client, "wr_iso_b@test.com", PASSWORD, "RunOrgB")
    org_b = _get_org_id(client, token_b)

    active = client.get(
        "/api/workspace/executions/active",
        headers=_auth_headers(token_b, org_b),
    )
    assert active.status_code == 200, active.text
    assert active.json() is None

    stop = client.post(
        f"/api/workspace/executions/{execution_id}/stop",
        headers=_auth_headers(token_b, org_b),
    )
    assert stop.status_code == 404

    stream = client.get(
        f"/api/workspace/executions/{execution_id}/stream",
        headers=_auth_headers(token_b, org_b),
    )
    assert stream.status_code == 404
