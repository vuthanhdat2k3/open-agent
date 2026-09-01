from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.tools.paths import safe_resolve
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.services.workspace_service import upsert_workspace_artifact

MAX_FILE_CHARS = 50_000
MAX_LIST_ENTRIES = 500
MAX_GREP_RESULTS = 200
MAX_GREP_CHARS = 50_000

# Directories we never recurse into during search.
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".codegraph", ".omo"}
# Binary extensions we skip to avoid garbage matches / slow reads.
BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".wav",
    ".bin",
    ".pyc",
    ".db",
    ".sqlite",
}


async def _write_file(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "error: missing 'path'"
    if content is None:
        return "error: missing 'content'"
    if ctx.emit:
        await ctx.emit({"stage": "writing", "path": path, "line": f"Writing {len(str(content))} chars to '{path}'...\n"})
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return f"error writing file: {e}"
    try:
        await upsert_workspace_artifact(
            ctx.db,
            org_id=ctx.org_id,
            path=target,
            workspace_dir=ctx.workspace_dir,
            source_tool="write_file",
            user_id=ctx.user_id,
            agent_id=ctx.agent_id,
            session_id=ctx.session_id,
            task_id=ctx.current_task_id,
            root_run_id=ctx.root_run_id,
        )
    except Exception:
        pass
    return f"wrote {len(str(content))} chars to {path}"


async def _list_dir(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "") or "."
    if ctx.emit:
        await ctx.emit({"stage": "listing", "path": path, "line": f"Listing directory '{path}'...\n"})
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    if not target.exists():
        return f"error: path not found: {path}"
    if target.is_file():
        target = target.parent
    try:
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except Exception as e:  # noqa: BLE001
        return f"error listing directory: {e}"
    lines: list[str] = []
    for p in entries[:MAX_LIST_ENTRIES]:
        if p.is_dir():
            lines.append(f"[dir]  {p.name}/")
        else:
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            lines.append(f"[file] {p.name} ({size} bytes)")
    if not lines:
        return f"(empty) {path}"
    if len(entries) > MAX_LIST_ENTRIES:
        lines.append(f"... {len(entries) - MAX_LIST_ENTRIES} more entries")
    return "\n".join(lines)


async def _search_files(args: dict[str, Any], ctx: ToolContext) -> str:
    pattern = args.get("pattern", "")
    glob = args.get("glob", "**/*")
    max_results = int(args.get("max_results", MAX_GREP_RESULTS))
    if not pattern:
        return "error: missing 'pattern'"
    if ctx.emit:
        await ctx.emit({"stage": "searching", "pattern": pattern, "line": f"Searching workspace for pattern: '{pattern}'...\n"})
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"error: invalid regex: {e}"

    base = Path(ctx.workspace_dir).resolve()
    matches: list[str] = []
    total = 0
    try:
        for f in base.glob(glob):
            if not f.is_file():
                continue
            if f.suffix.lower() in BINARY_EXTS:
                continue
            rel = f.relative_to(base)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    total += 1
                    if len(matches) < max_results:
                        matches.append(f"{rel}:{i}: {line}")
                    if sum(len(m) for m in matches) > MAX_GREP_CHARS:
                        break
            if len(matches) >= max_results:
                break
    except Exception as e:  # noqa: BLE001
        return f"error searching files: {e}"

    if not matches:
        return "No matches found"
    out = "\n".join(matches)
    if total > len(matches):
        out += f"\n... ({total - len(matches)} more matches, {total} total)"
    return out


register(
    ToolSpec(
        name="write_file",
        description=(
            "Write text content to a file inside the workspace. Creates parent "
            "directories as needed. Provide 'path' (relative) and 'content'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path inside the workspace",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write",
                },
            },
            "required": ["path", "content"],
        },
        run=_write_file,
        risk_tier=RiskTier.write,
    )
)

register(
    ToolSpec(
        name="list_dir",
        description=(
            "List files and directories inside the workspace at a relative "
            "'path' (defaults to the workspace root)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path inside the workspace (optional)",
                }
            },
            "required": [],
        },
        run=_list_dir,
        risk_tier=RiskTier.read,
    )
)

register(
    ToolSpec(
        name="search_files",
        description=(
            "Search file contents in the workspace using a regex 'pattern'. "
            "Optional 'glob' filters which files to scan (e.g. '*.py'); "
            "'max_results' caps the number of hits returned."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression to search for",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob to filter files (default '**/*')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matches to return",
                },
            },
            "required": ["pattern"],
        },
        run=_search_files,
        risk_tier=RiskTier.read,
    )
)

async def _preview_web_artifact(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "")
    if not path:
        return "error: missing 'path'"
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    if not target.exists():
        return f"error: file not found: {path}"
    if not target.is_file():
        return f"error: path is not a file: {path}"

    suffix = target.suffix.lower()
    if suffix not in {".html", ".htm", ".svg"}:
        return f"error: preview_web_artifact only supports web artifacts (.html, .htm, .svg), got '{suffix}'"

    size_bytes = target.stat().st_size
    if ctx.emit:
        await ctx.emit({
            "stage": "previewing",
            "path": path,
            "line": f"Launching live interactive web preview for '{path}' ({size_bytes} bytes)...\n",
        })

    try:
        await upsert_workspace_artifact(
            ctx.db,
            org_id=ctx.org_id,
            path=target,
            workspace_dir=ctx.workspace_dir,
            source_tool="preview_web_artifact",
            user_id=ctx.user_id,
            agent_id=ctx.agent_id,
            session_id=ctx.session_id,
            task_id=ctx.current_task_id,
            root_run_id=ctx.root_run_id,
        )
    except Exception:
        pass

    return f"Live interactive web preview ready for '{path}' ({size_bytes} bytes). The user can now view and interact with the rendered web application directly in the Live Preview panel."


register(
    ToolSpec(
        name="preview_web_artifact",
        description=(
            "Launch a live interactive browser preview for a web artifact (.html, .htm, .svg) "
            "in the workspace. Allows the user to view, test, and interact with 3D scenes (Three.js), "
            "animations, games, and web layouts directly."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the .html or .svg file in the workspace",
                }
            },
            "required": ["path"],
        },
        run=_preview_web_artifact,
        risk_tier=RiskTier.read,
    )
)

