"""Google Drive MCP server for open-agent.

Exposes two tools that open-agent surfaces in chat:

* ``list_drive_files`` — list files on the connected Google Drive.
* ``get_drive_file`` / ``read_file_tool`` — find a file by id or name and return
  its text content (converted to Markdown via MarkItDown) so it can be shown in
  the chat.

Transport: stdio (the default FastMCP transport), which is exactly what
open-agent's ``McpClient`` expects (``StdioServerParameters`` → ``stdio_client``).

Configuration (environment variables):
    GOOGLE_CREDENTIALS_PATH   path to the OAuth client_secret JSON (default: credentials.json)
    GOOGLE_TOKEN_PATH         path where the OAuth token is cached (default: token.json)
    GOOGLE_SERVICE_ACCOUNT_PATH  optional: use a service-account JSON instead of browser OAuth
    DRIVE_ROOT_FOLDER_ID      optional: restrict every operation to this Drive folder
    DRIVE_PAGE_SIZE           default page size for list_drive_files (default: 20)
    DRIVE_MAX_OUTPUT_CHARS    truncate file text beyond this many chars (default: 40000)

Auth: run ``python auth.py`` once to perform the browser OAuth flow and cache
``token.json``. The server reuses that token. If no token exists when a tool is
first called, it triggers the same browser flow automatically.
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# ---------------------------------------------------------------------------
# Configuration (read once from the environment open-agent passes to the child)
# ---------------------------------------------------------------------------
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")
SERVICE_ACCOUNT_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH")
DRIVE_ROOT_FOLDER_ID = os.environ.get("DRIVE_ROOT_FOLDER_ID", "")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))
DEFAULT_PAGE_SIZE = int(os.environ.get("DRIVE_PAGE_SIZE", "20"))
MAX_OUTPUT_CHARS = int(os.environ.get("DRIVE_MAX_OUTPUT_CHARS", "40000"))

mcp = FastMCP("drive-mcp", host=MCP_HOST, port=MCP_PORT)

# Lazily-initialised Drive API service (created on first tool call).
_drive_service = None

# Google "native" formats can't be downloaded directly; export them to a format
# MarkItDown understands.
NATIVE_EXPORT = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}

MIME_EXT = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "application/json": ".json",
    "text/html": ".html",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


# ---------------------------------------------------------------------------
# Drive service + auth
# ---------------------------------------------------------------------------
def _build_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds: Optional[Credentials] = None

    if SERVICE_ACCOUNT_PATH and Path(SERVICE_ACCOUNT_PATH).exists():
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_PATH, scopes=[DRIVE_READONLY_SCOPE]
        )
    else:
        token_file = Path(TOKEN_PATH)
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, [DRIVE_READONLY_SCOPE])
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(CREDENTIALS_PATH).exists():
                    raise FileNotFoundError(
                        f"Missing OAuth credentials at {CREDENTIALS_PATH}. "
                        "Download the client_secret JSON from Google Cloud Console "
                        "or run `python auth.py` to authenticate."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_PATH, scopes=[DRIVE_READONLY_SCOPE]
                )
                creds = flow.run_local_server(port=0)
            # Persist (best-effort: a read-only mount must not crash the server).
            try:
                Path(TOKEN_PATH).write_text(creds.to_json())
            except OSError:
                pass

    _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_service


def _root_filter() -> list[str]:
    if DRIVE_ROOT_FOLDER_ID:
        return [f"'{DRIVE_ROOT_FOLDER_ID}' in parents"]
    return []


# ---------------------------------------------------------------------------
# File download + content extraction
# ---------------------------------------------------------------------------
def _download_file(service, file_id: str, mime_type: str, name: str):
    import googleapiclient.http

    if mime_type.startswith("application/vnd.google-apps."):
        export_mime, ext = NATIVE_EXPORT.get(mime_type, ("application/pdf", ".pdf"))
        req = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        req = service.files().get_media(fileId=file_id)
        ext = Path(name).suffix or MIME_EXT.get(mime_type, ".bin")

    fh = io.BytesIO()
    downloader = googleapiclient.http.MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read(), ext


def _to_markdown(data: bytes, ext: str) -> str:
    from markitdown import MarkItDown

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        result = MarkItDown().convert(path)
        return result.text_content or ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _resolve_file_id(service, name: str) -> Optional[str]:
    safe = name.replace("'", "")
    q = _root_filter()
    q.append(f"name contains '{safe}'")
    res = (
        service.files()
        .list(q=" and ".join(q), pageSize=10, fields="files(id,name,modifiedTime)", orderBy="modifiedTime desc")
        .execute()
    )
    files = res.get("files", [])
    if not files:
        return None
    name_l = name.lower()
    for f in files:
        if f["name"].lower() == name_l:
            return f["id"]
    return files[0]["id"]


# ---------------------------------------------------------------------------
# Tool cores (synchronous; run inside a thread by the async wrappers)
# ---------------------------------------------------------------------------
def _list_core(query: str, page_size: int) -> str:
    service = _build_service()
    n = page_size or DEFAULT_PAGE_SIZE
    q = _root_filter()
    if query:
        safe = query.replace("'", "")
        q.append(f"name contains '{safe}'")
    qstr = " and ".join(q) if q else None

    results = (
        service.files()
        .list(
            pageSize=n,
            q=qstr,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    files = results.get("files", [])
    if not files:
        return "No files found on Drive" + (f" matching '{query}'." if query else ".")

    lines = [
        "| Name | Type | Size | Modified | ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in files:
        size = f.get("size") or "-"
        lines.append(
            f"| {f['name']} | {f.get('mimeType', '')} | {size} | {f.get('modifiedTime', '')} | {f['id']} |"
        )
    return "\n".join(lines)


def _read_core(file_id: str, name: str) -> str:
    if not file_id and not name:
        return "error: provide either file_id or name."
    service = _build_service()

    if not file_id:
        file_id = _resolve_file_id(service, name)
        if not file_id:
            return f"error: no Drive file found matching '{name}'."

    meta = service.files().get(fileId=file_id, fields="id,name,mimeType,size").execute()
    data, ext = _download_file(service, file_id, meta.get("mimeType", ""), meta.get("name", ""))
    text = _to_markdown(data, ext)

    if not text.strip():
        return (
            f"(file '{meta.get('name')}' was read but contained no extractable text; "
            f"mimeType={meta.get('mimeType')})"
        )
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n\n… (truncated; total {len(text)} chars)"
    return f"# {meta.get('name')}\n\n{text}"


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_drive_files(query: str = "", page_size: int = 0) -> str:
    """List files on the connected Google Drive.

    Args:
        query: Optional free-text filter; matches file names containing this text.
        page_size: Max files to return (defaults to DRIVE_PAGE_SIZE env, 20).

    Returns:
        A Markdown table of files (name, type, size, modified, id).
    """
    return await asyncio.to_thread(_list_core, query, page_size)


@mcp.tool()
async def get_drive_file(file_id: str = "", name: str = "") -> str:
    """Find a file on Google Drive by id or name and return its text content.

    Reads the file, converts it to Markdown via MarkItDown (pdf/docx/xlsx/pptx/
    csv/txt/html/images), and returns the text so it can be shown in chat.

    Args:
        file_id: Exact Google Drive file ID (preferred). Ignores name when set.
        name: File name or fragment to search for; the best match is opened.

    Returns:
        The file's Markdown text, or an error message.
    """
    return await asyncio.to_thread(_read_core, file_id, name)


@mcp.tool()
async def read_file_tool(file_id: str = "", name: str = "") -> str:
    """Alias of get_drive_file: read a Drive file by id or name and show it in chat.

    Args:
        file_id: Exact Google Drive file ID (preferred). Ignores name when set.
        name: File name or fragment to search for; the best match is opened.

    Returns:
        The file's Markdown text, or an error message.
    """
    return await asyncio.to_thread(_read_core, file_id, name)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "sse":
        # Network mode: open-agent connects via transport="sse", url="http://host:port/sse".
        # Requires GOOGLE_TOKEN_PATH to already exist (run `python auth.py` on the host first).
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
