from __future__ import annotations

import io
import tarfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.tools.registry import get_tool, list_tools
from app.core.tools.sandbox import build_workspace_archive
from app.core.tools.types import ToolContext
from app.db.base import Base


def _ctx(workspace_dir: str) -> ToolContext:
    # Tools added here do not touch the DB; pass None for the session.
    return ToolContext(db=None, workspace_dir=workspace_dir)


async def test_write_list_search(tmp_path: Path) -> None:
    ctx = _ctx(str(tmp_path))
    res = await get_tool("write_file").run(
        {"path": "a/b.txt", "content": "hello world\nfoo bar"}, ctx
    )
    assert "wrote" in res
    assert (tmp_path / "a" / "b.txt").exists()

    listing = await get_tool("list_dir").run({"path": "a"}, ctx)
    assert "b.txt" in listing

    found = await get_tool("search_files").run({"pattern": "foo", "glob": "**/*.txt"}, ctx)
    assert "b.txt" in found and "foo bar" in found


async def test_sandbox_rejects_traversal(tmp_path: Path) -> None:
    ctx = _ctx(str(tmp_path))
    res = await get_tool("write_file").run({"path": "../../evil.txt", "content": "x"}, ctx)
    assert "escapes" in res
    assert not (tmp_path.parent / "evil.txt").exists()


async def test_run_code_workspace_archive_includes_existing_files(tmp_path: Path) -> None:
    (tmp_path / "draw_house.py").write_text("print('house')", encoding="utf-8")

    archive_bytes = build_workspace_archive(
        str(tmp_path),
        "script.py",
        "exec(open('draw_house.py').read())",
    )

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        names = archive.getnames()
        assert "draw_house.py" in names
        assert "script.py" in names
        script = archive.extractfile("script.py")
        assert script is not None
        assert script.read().decode("utf-8") == "exec(open('draw_house.py').read())"


async def test_run_shell_echo(tmp_path: Path, monkeypatch) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self, _archive: bytes):
            return b"hello-agent\n", None

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr("app.core.tools.sandbox._docker_available", lambda: True)
    monkeypatch.setattr(
        "app.core.tools.shell.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    ctx = _ctx(str(tmp_path))
    res = await get_tool("run_shell").run({"cmd": "echo hello-agent"}, ctx)
    assert "hello-agent" in res
    assert "exit code: 0" in res


async def test_all_builtins_registered() -> None:
    names = {t.name for t in list_tools()}
    for expected in {
        "read_attachment",
        "web_fetch",
        "memory_store",
        "memory_recall",
        "call_agent",
        "write_file",
        "list_dir",
        "search_files",
        "run_shell",
        "web_search",
        "save_memory",
        "call_memory",
    }:
        assert expected in names


async def test_save_and_call_memory() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        ctx = ToolContext(db=session, agent_id="agent-1", workspace_dir="/tmp")
        await get_tool("save_memory").run(
            {"memory_type": "profile", "attribute": "name", "value": "Dat"}, ctx
        )
        await get_tool("save_memory").run(
            {"memory_type": "preference", "attribute": "preferred_language", "value": "Python"}, ctx
        )
        res = await get_tool("call_memory").run({"query": "python"}, ctx)
        assert "Python" in res and "language" in res
        res2 = await get_tool("call_memory").run({"attribute": "name"}, ctx)
        assert "Dat" in res2
        res3 = await get_tool("call_memory").run({}, ctx)
        assert "Dat" in res3 and "Python" in res3
    await engine.dispose()
