from __future__ import annotations

from pathlib import Path

from app.core.tools.paths import safe_resolve
from app.core.tools.registry import list_tools, get_tool
from app.core.tools.types import ToolContext


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

    found = await get_tool("search_files").run(
        {"pattern": "foo", "glob": "**/*.txt"}, ctx
    )
    assert "b.txt" in found and "foo bar" in found


async def test_sandbox_rejects_traversal(tmp_path: Path) -> None:
    ctx = _ctx(str(tmp_path))
    res = await get_tool("write_file").run(
        {"path": "../../evil.txt", "content": "x"}, ctx
    )
    assert "escapes" in res
    assert not (tmp_path.parent / "evil.txt").exists()


async def test_run_shell_echo(tmp_path: Path) -> None:
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
    ctx = _ctx("/tmp")
    await get_tool("save_memory").run({"key": "name", "value": "Dat"}, ctx)
    await get_tool("save_memory").run(
        {"key": "preferred_language", "value": "Python"}, ctx
    )
    res = await get_tool("call_memory").run({"query": "python"}, ctx)
    assert "Python" in res and "preferred_language" in res
    res2 = await get_tool("call_memory").run({"key": "name"}, ctx)
    assert "Dat" in res2
    res3 = await get_tool("call_memory").run({}, ctx)
    assert "Dat" in res3 and "Python" in res3
