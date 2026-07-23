from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.tools.paths import safe_resolve
from app.core.tools.registry import register
from app.core.tools.types import ToolContext, ToolSpec

MAX_FILE_CHARS = 50_000
MAX_LIST_ENTRIES = 500
MAX_GREP_RESULTS = 200
MAX_GREP_CHARS = 50_000

# Directories we never recurse into during search.
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".codegraph", ".omo"}
# Binary extensions we skip to avoid garbage matches / slow reads.
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".tgz", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf",
    ".eot", ".mp4", ".mp3", ".wav", ".bin", ".pyc", ".db", ".sqlite",
}


async def _write_file(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "error: missing 'path'"
    if content is None:
        return "error: missing 'content'"
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return f"error writing file: {e}"
    return f"wrote {len(str(content))} chars to {path}"


async def _list_dir(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "") or "."
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    if not target.exists():
        return f"error: path not found: {path}"
    if target.is_file():
        target = target.parent
    try:
        entries = sorted(
            target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
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
    )
)
