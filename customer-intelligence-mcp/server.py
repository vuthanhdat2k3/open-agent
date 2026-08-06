from __future__ import annotations

import base64
import html
import json
import os
import re
from datetime import datetime, timezone
from email.utils import getaddresses
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

try:
    from mcp.server.transport_security import TransportSecuritySettings

    mcp = FastMCP(
        "customer-intelligence-mcp",
        transport_security=TransportSecuritySettings(
            allowed_hosts=["localhost:*", "127.0.0.1:*", "customer-intelligence-mcp:*"],
            allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://customer-intelligence-mcp:*"],
        ),
    )
except (ImportError, TypeError, AttributeError):
    mcp = FastMCP("customer-intelligence-mcp")
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
CALENDAR_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
DDG_URL = "https://html.duckduckgo.com/html/"
MAX_BODY_CHARS = int(os.environ.get("CI_MCP_MAX_BODY_CHARS", "200000"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ok(data: Any, **extra: Any) -> str:
    return _json({"status": "ok", "data": data, "warnings": [], "sources": [], **extra})


def _error(message: str, status: str = "error") -> str:
    return _json({"status": status, "data": None, "warnings": [message], "sources": []})


def _headers(access_token: str) -> dict[str, str]:
    if not access_token:
        raise ValueError("access_token is required")
    return {"Authorization": f"Bearer {access_token}"}


async def _request(
    method: str,
    url: str,
    access_token: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.request(
            method,
            url,
            headers=_headers(access_token),
            params=params,
            json=body,
        )
        response.raise_for_status()
        return response.json() if response.content else {}


async def _drive_json(method: str, path: str, access_token: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.request(method, f"{DRIVE_API}{path}", headers=_headers(access_token), params=params, json=body)
        response.raise_for_status()
        return response.json() if response.content else {}


def _multipart_body(metadata: dict[str, Any], content: str, mime_type: str) -> tuple[bytes, str]:
    boundary = "openagent-drive-boundary"
    encoded = content.encode("utf-8")
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + json.dumps(metadata).encode()
        + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode()
        + encoded
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/related; boundary={boundary}"


def _calendar_event(raw: dict[str, Any]) -> dict[str, Any]:
    start = raw.get("start", {}).get("dateTime") or raw.get("start", {}).get("date")
    end = raw.get("end", {}).get("dateTime") or raw.get("end", {}).get("date")
    return {
        "provider_event_id": raw.get("id", ""),
        "title": raw.get("summary", ""),
        "start_at": start,
        "end_at": end,
        "attendees": [a.get("email", "") for a in raw.get("attendees", [])],
        "organizer": raw.get("organizer", {}).get("email"),
        "description": raw.get("description"),
        "location": raw.get("location"),
    }


async def _drive_upload(method: str, path: str, access_token: str, *, content: str, mime_type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    body, content_type = _multipart_body(metadata or {}, content, mime_type)
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.request(method, f"{DRIVE_UPLOAD_API}{path}", headers={**_headers(access_token), "Content-Type": content_type}, params={"uploadType": "multipart"}, content=body)
        response.raise_for_status()
        return response.json() if response.content else {}


def _decode_body(value: str | None) -> str:
    if not value:
        return ""
    try:
        return base64.urlsafe_b64decode(value.encode("ascii") + b"===").decode(
            "utf-8", errors="replace"
        )
    except (ValueError, UnicodeError):
        return ""


def _gmail_text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain":
        return _decode_body(payload.get("body", {}).get("data"))
    return "\n".join(_gmail_text(part) for part in payload.get("parts", []))[:MAX_BODY_CHARS]


def _gmail_message(raw: dict[str, Any]) -> dict[str, Any]:
    headers = {item["name"].lower(): item.get("value", "") for item in raw.get("payload", {}).get("headers", [])}
    sender = getaddresses([headers.get("from", "")])[0] if headers.get("from") else ("", "")
    recipients = [address for _, address in getaddresses([headers.get("to", "")]) if address]
    sender_email = sender[1]
    received_ms = raw.get("internalDate")
    received_at = (
        datetime.fromtimestamp(int(received_ms) / 1000, tz=timezone.utc).isoformat()
        if received_ms
        else datetime.now(timezone.utc).isoformat()
    )
    return {
        "provider": "gmail",
        "provider_message_id": raw.get("id", ""),
        "thread_id": raw.get("threadId"),
        "sender_name": sender[0] or None,
        "sender_email": sender_email,
        "sender_domain": sender_email.rsplit("@", 1)[-1].lower() if "@" in sender_email else "",
        "recipients": recipients,
        "subject": headers.get("subject", ""),
        "body_text": _gmail_text(raw.get("payload", {}))[:MAX_BODY_CHARS],
        "body_html": None,
        "attachments": [
            {
                "filename": part.get("filename", "attachment"),
                "content_type": part.get("mimeType", "application/octet-stream"),
                "size_bytes": int(part.get("body", {}).get("size", 0)),
            }
            for part in raw.get("payload", {}).get("parts", [])
            if part.get("filename")
        ],
        "received_at": received_at,
        "headers": headers,
    }


@mcp.tool()
async def email_list_new(
    provider: str,
    access_token: str,
    cursor: str = "",
    max_results: int = 20,
) -> str:
    """List unread/inbox messages using the user's delegated provider token."""
    try:
        max_results = max(1, min(max_results, 50))
        if provider == "gmail":
            data = await _request(
                "GET",
                f"{GMAIL_API}/messages",
                access_token,
                params={"q": "in:inbox", "maxResults": max_results, **({"pageToken": cursor} if cursor else {})},
            )
            messages = []
            for item in data.get("messages", []):
                raw = await _request("GET", f"{GMAIL_API}/messages/{item['id']}", access_token, params={"format": "full"})
                messages.append(_gmail_message(raw))
            return _ok({"messages": messages, "new_cursor": data.get("nextPageToken"), "has_more": bool(data.get("nextPageToken"))})
        return _error(f"unsupported email provider: {provider}; only gmail is enabled")
    except Exception as exc:  # noqa: BLE001 - MCP tools return typed errors.
        return _error(f"email list failed: {type(exc).__name__}")


@mcp.tool()
async def email_get(provider: str, access_token: str, provider_message_id: str) -> str:
    try:
        if provider == "gmail":
            raw = await _request("GET", f"{GMAIL_API}/messages/{provider_message_id}", access_token, params={"format": "full"})
            return _ok(_gmail_message(raw))
        return _error(f"unsupported email provider: {provider}; only gmail is enabled")
    except Exception as exc:  # noqa: BLE001
        return _error(f"email get failed: {type(exc).__name__}")


@mcp.tool()
async def email_create_draft(provider: str, access_token: str, to: str, subject: str, body: str) -> str:
    try:
        if provider == "gmail":
            import base64 as b64
            from email.message import EmailMessage

            message = EmailMessage()
            message["To"] = to
            message["Subject"] = subject
            message.set_content(body)
            encoded = b64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            data = await _request("POST", f"{GMAIL_API}/drafts", access_token, body={"message": {"raw": encoded}})
            return _ok({"draft_id": data.get("id", "")})
        return _error(f"unsupported email provider: {provider}; only gmail is enabled")
    except Exception as exc:  # noqa: BLE001
        return _error(f"draft creation failed: {type(exc).__name__}")


@mcp.tool()
async def email_send(provider: str, access_token: str, draft_id: str, idempotency_key: str) -> str:
    try:
        if provider == "gmail":
            data = await _request("POST", f"{GMAIL_API}/drafts/send", access_token, body={"id": draft_id})
            return _ok({"send_id": data.get("id", "")})
        return _error(f"unsupported email provider: {provider}; only gmail is enabled")
    except Exception as exc:  # noqa: BLE001
        return _error(f"email send failed: {type(exc).__name__}")


@mcp.tool()
async def calendar_list_events(
    provider: str,
    access_token: str,
    from_: str,
    to: str,
    max_results: int = 25,
) -> str:
    try:
        max_results = max(1, min(max_results, 50))
        if provider == "google":
            data = await _request("GET", CALENDAR_API, access_token, params={"timeMin": from_, "timeMax": to, "singleEvents": "true", "orderBy": "startTime", "maxResults": max_results})
            events = []
            for item in data.get("items", []):
                events.append(_calendar_event(item))
            return _ok(events)
        return _error(f"unsupported calendar provider: {provider}; only google is enabled")
    except Exception as exc:  # noqa: BLE001
        return _error(f"calendar lookup failed: {type(exc).__name__}")


@mcp.tool()
async def calendar_get_event(provider: str, access_token: str, provider_event_id: str) -> str:
    try:
        if provider != "google":
            return _error(f"unsupported calendar provider: {provider}; only google is enabled")
        return _ok(_calendar_event(await _request("GET", f"{CALENDAR_API}/{provider_event_id}", access_token)))
    except Exception as exc:  # noqa: BLE001
        return _error(f"calendar get failed: {type(exc).__name__}")


def _calendar_body(summary: str, start: str | None = None, end: str | None = None, description: str = "", location: str = "", attendees: list[str] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"summary": summary}
    if start:
        body["start"] = {"dateTime": start}
    if end:
        body["end"] = {"dateTime": end}
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees is not None:
        body["attendees"] = [{"email": email} for email in attendees]
    return body


@mcp.tool()
async def calendar_create_event(provider: str, access_token: str, summary: str, start: str, end: str, description: str = "", location: str = "", attendees: list[str] | None = None) -> str:
    try:
        if provider != "google":
            return _error(f"unsupported calendar provider: {provider}; only google is enabled")
        created = await _request("POST", CALENDAR_API, access_token, body=_calendar_body(summary, start, end, description, location, attendees or []))
        return _ok(_calendar_event(created))
    except Exception as exc:  # noqa: BLE001
        return _error(f"calendar create failed: {type(exc).__name__}")


@mcp.tool()
async def calendar_update_event(provider: str, access_token: str, provider_event_id: str, summary: str | None = None, start: str | None = None, end: str | None = None, description: str = "", location: str = "", attendees: list[str] | None = None) -> str:
    try:
        if provider != "google":
            return _error(f"unsupported calendar provider: {provider}; only google is enabled")
        current = await _request("GET", f"{CALENDAR_API}/{provider_event_id}", access_token)
        body = _calendar_body(summary or current.get("summary", ""), start or current.get("start", {}).get("dateTime"), end or current.get("end", {}).get("dateTime"), description or current.get("description", ""), location or current.get("location", ""), attendees if attendees is not None else [a.get("email", "") for a in current.get("attendees", [])])
        updated = await _request("PATCH", f"{CALENDAR_API}/{provider_event_id}", access_token, body=body)
        return _ok(_calendar_event(updated))
    except Exception as exc:  # noqa: BLE001
        return _error(f"calendar update failed: {type(exc).__name__}")


@mcp.tool()
async def calendar_delete_event(provider: str, access_token: str, provider_event_id: str) -> str:
    try:
        if provider != "google":
            return _error(f"unsupported calendar provider: {provider}; only google is enabled")
        await _request("DELETE", f"{CALENDAR_API}/{provider_event_id}", access_token)
        return _ok({"provider_event_id": provider_event_id, "deleted": True})
    except Exception as exc:  # noqa: BLE001
        return _error(f"calendar delete failed: {type(exc).__name__}")


async def _ddg(query: str, limit: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.post(DDG_URL, data={"q": query}, headers={"User-Agent": "OpenAgent-CI-MCP/1.0"})
        response.raise_for_status()
    titles = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', response.text, re.S)
    return [{"url": url, "title": re.sub(r"<[^>]+>", "", html.unescape(title)).strip(), "publisher": url.split("/")[2] if "://" in url else "", "published_date": None, "retrieved_date": datetime.now(timezone.utc).date().isoformat(), "excerpt": "", "domain": url.split("/")[2] if "://" in url else ""} for url, title in titles[: max(1, min(limit, 10))]]


@mcp.tool()
async def web_search(query: str, limit: int = 5) -> str:
    try:
        return _ok(await _ddg(query, limit))
    except Exception as exc:  # noqa: BLE001
        return _error(f"web search unavailable: {type(exc).__name__}", "research_unavailable")


@mcp.tool()
async def news_search(query: str, limit: int = 5, lookback_days: int = 30) -> str:
    try:
        hits = await _ddg(f"{query} news", limit)
        dated = [hit for hit in hits if hit.get("published_date")]
        if not dated:
            return _error("news provider returned no dated results", "research_unavailable")
        return _ok(dated)
    except Exception as exc:  # noqa: BLE001
        return _error(f"news search unavailable: {type(exc).__name__}", "research_unavailable")


@mcp.tool()
async def company_search(query: str, limit: int = 5) -> str:
    api_url = os.environ.get("CI_COMPANY_API_URL", "")
    api_key = os.environ.get("CI_COMPANY_API_KEY", "")
    if not api_url or not api_key:
        return _error("company provider is not configured", "research_unavailable")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{api_url.rstrip('/')}/search", params={"query": query, "limit": limit}, headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
            return _ok(response.json())
    except Exception as exc:  # noqa: BLE001
        return _error(f"company search unavailable: {type(exc).__name__}", "research_unavailable")


@mcp.tool()
async def company_get(company_id: str) -> str:
    api_url = os.environ.get("CI_COMPANY_API_URL", "")
    api_key = os.environ.get("CI_COMPANY_API_KEY", "")
    if not api_url or not api_key:
        return _error("company provider is not configured", "research_unavailable")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{api_url.rstrip('/')}/companies/{company_id}", headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
            return _ok(response.json())
    except Exception as exc:  # noqa: BLE001
        return _error(f"company lookup unavailable: {type(exc).__name__}", "research_unavailable")


@mcp.tool()
async def drive_list_files(access_token: str, query: str = "", page_size: int = 20) -> str:
    try:
        page_size = max(1, min(page_size, 100))
        params: dict[str, Any] = {"pageSize": page_size, "orderBy": "modifiedTime desc", "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)", "q": "trashed = false"}
        if query:
            safe_query = query.replace("'", "\\'")
            params["q"] += f" and name contains '{safe_query}'"
        return _ok((await _drive_json("GET", "/files", access_token, params=params)).get("files", []))
    except Exception as exc:  # noqa: BLE001
        return _error(f"drive list failed: {type(exc).__name__}")


@mcp.tool()
async def drive_get_file(access_token: str, file_id: str, max_chars: int = 50000) -> str:
    try:
        metadata = await _drive_json("GET", f"/files/{file_id}", access_token, params={"fields": "id,name,mimeType,size,modifiedTime,webViewLink"})
        mime_type = metadata.get("mimeType", "")
        async with httpx.AsyncClient(timeout=30.0) as client:
            if mime_type.startswith("application/vnd.google-apps."):
                response = await client.get(f"{DRIVE_API}/files/{file_id}/export", headers=_headers(access_token), params={"mimeType": "text/plain"})
            else:
                response = await client.get(f"{DRIVE_API}/files/{file_id}", headers=_headers(access_token), params={"alt": "media"})
            response.raise_for_status()
        text = response.text[: max(1, min(max_chars, MAX_BODY_CHARS))]
        return _ok({"metadata": metadata, "content": text})
    except Exception as exc:  # noqa: BLE001
        return _error(f"drive read failed: {type(exc).__name__}")


@mcp.tool()
async def drive_create_file(access_token: str, name: str, content: str, mime_type: str = "text/plain", parent_id: str = "") -> str:
    try:
        metadata: dict[str, Any] = {"name": name}
        if parent_id:
            metadata["parents"] = [parent_id]
        created = await _drive_upload("POST", "", access_token, content=content, mime_type=mime_type, metadata=metadata)
        return _ok(created)
    except Exception as exc:  # noqa: BLE001
        return _error(f"drive create failed: {type(exc).__name__}")


@mcp.tool()
async def drive_update_file(access_token: str, file_id: str, content: str = "", name: str = "", mime_type: str = "text/plain") -> str:
    try:
        metadata = {"name": name} if name else {}
        updated = await _drive_upload("PATCH", f"/{file_id}", access_token, content=content, mime_type=mime_type, metadata=metadata)
        return _ok(updated)
    except Exception as exc:  # noqa: BLE001
        return _error(f"drive update failed: {type(exc).__name__}")


@mcp.tool()
async def drive_delete_file(access_token: str, file_id: str) -> str:
    try:
        await _drive_json("DELETE", f"/files/{file_id}", access_token)
        return _ok({"file_id": file_id, "deleted": True})
    except Exception as exc:  # noqa: BLE001
        return _error(f"drive delete failed: {type(exc).__name__}")


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "sse").lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("MCP_PORT", "8301"))
        mcp.run(transport="sse")
