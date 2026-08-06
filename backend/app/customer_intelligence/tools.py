from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import get_settings
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.customer_intelligence.contracts import (
    CALENDAR_GET_EVENT_SCHEMA,
    CALENDAR_LIST_EVENTS_SCHEMA,
    COMPANY_GET_SCHEMA,
    COMPANY_SEARCH_SCHEMA,
    DRIVE_CREATE_FILE_SCHEMA,
    DRIVE_DELETE_FILE_SCHEMA,
    DRIVE_GET_FILE_SCHEMA,
    DRIVE_LIST_FILES_SCHEMA,
    DRIVE_UPDATE_FILE_SCHEMA,
    EMAIL_CREATE_DRAFT_SCHEMA,
    EMAIL_GET_SCHEMA,
    EMAIL_LIST_NEW_SCHEMA,
    EMAIL_SEND_SCHEMA,
    NEWS_SEARCH_SCHEMA,
)
from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
from app.repositories.customer_intelligence import (
    CalendarConnectionRepository,
    DriveConnectionRepository,
    EmailConnectionRepository,
)


def _enabled() -> bool:
    return get_settings().customer_intelligence_enabled


async def _connected_provider(ctx: ToolContext, org_id: str, provider: str = "gmail"):
    if not ctx.user_id:
        raise ValueError("user context is required for email connection access")
    conn_repo = EmailConnectionRepository(ctx.db)
    conns = await conn_repo.list(org_id)
    conn = next(
        (
            c
            for c in conns
            if c.status == "connected"
            and c.provider == provider
            and c.created_by_user_id == ctx.user_id
        ),
        None,
    )
    if conn is None or not conn.credentials_enc:
        raise ValueError("no connected email account")
    creds = await load_fresh_credentials(ctx.db, conn)
    return conn, bind_email_provider(get_email_provider(conn.provider), creds)


async def _connected_calendar(ctx: ToolContext, org_id: str):
    conn = await CalendarConnectionRepository(ctx.db).get_connected(org_id, ctx.user_id)
    if conn is None or not conn.credentials_enc:
        raise ValueError("no connected calendar account")
    from app.customer_intelligence.providers.research import (
        bind_calendar_provider,
        get_calendar_provider,
    )

    creds = await load_fresh_credentials(ctx.db, conn)
    return conn, bind_calendar_provider(get_calendar_provider(), creds)


async def _connected_drive(ctx: ToolContext, org_id: str):
    conn = await DriveConnectionRepository(ctx.db).get_connected(org_id, ctx.user_id)
    if conn is None or not conn.credentials_enc:
        raise ValueError("no connected Google Drive account")
    from app.customer_intelligence.providers.drive import McpDriveProvider

    creds = await load_fresh_credentials(ctx.db, conn)
    return conn, McpDriveProvider(creds)


async def _email_list_new(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
    except ValueError as e:
        return f"error: {e}"
    page = await provider.list_new(cursor=args.get("cursor"), max_results=args.get("max_results", 20))
    if not page.messages:
        return "No new email"
    return "\n".join(
        f"{m.provider_message_id} | {m.sender_email} | {m.subject}" for m in page.messages
    )


async def _email_get(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
    except ValueError as e:
        return f"error: {e}"
    try:
        msg = await provider.get_message(args["provider_message_id"])
    except KeyError as e:
        return f"error: {e}"
    return f"{msg.sender_email}: {msg.subject}\n\n{msg.body_text[:5000]}"


async def _email_create_draft(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
    except ValueError as e:
        return f"error: {e}"
    try:
        return await provider.create_draft(
            to=args["to"],
            subject=args["subject"],
            body=args["body"],
            in_reply_to=args.get("in_reply_to"),
        )
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


async def _email_send(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    return "error: email_send must use the case approval delivery endpoint"


async def _news_search(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    from app.customer_intelligence.providers.research import get_web_provider

    hits = await get_web_provider().news_search(
        args["query"], limit=args.get("limit", 5), lookback_days=args.get("lookback_days", 30)
    )
    if not hits:
        return "no news results"
    return "\n".join(f"{h.title} ({h.publisher}) {h.url}" for h in hits)


async def _company_search(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    from app.customer_intelligence.providers.research import get_company_provider

    records = await get_company_provider().company_search(args["query"], limit=args.get("limit", 5))
    if not records:
        return "no company found"
    return "\n".join(f"{r.canonical_name} ({r.company_id})" for r in records)


async def _company_get(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    from app.customer_intelligence.providers.research import get_company_provider

    rec = await get_company_provider().company_get(args["company_id"])
    if rec is None:
        return "company not found"
    return f"{rec.canonical_name} | {rec.industry} | {', '.join(rec.products)}"


async def _drive_list_files(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, drive = await _connected_drive(ctx, ctx.org_id or "")
        files = await drive.list_files(args.get("query", ""), args.get("page_size", 20))
        return "no Drive files" if not files else "\n".join(f"{item.get('id')} | {item.get('name')} | {item.get('mimeType', '')}" for item in files)
    except Exception as exc:  # noqa: BLE001
        return f"error: drive list failed: {type(exc).__name__}"


async def _drive_get_file(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, drive = await _connected_drive(ctx, ctx.org_id or "")
        result = await drive.get_file(args["file_id"], args.get("max_chars", 50000))
        return f"{result.get('metadata', {}).get('name', args['file_id'])}\n\n{result.get('content', '')}"
    except Exception as exc:  # noqa: BLE001
        return f"error: drive read failed: {type(exc).__name__}"


async def _drive_create_file(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, drive = await _connected_drive(ctx, ctx.org_id or "")
        result = await drive.create_file(args["name"], args["content"], args.get("mime_type", "text/plain"), args.get("parent_id", ""))
        return f"created Drive file {result.get('id', '')}"
    except Exception as exc:  # noqa: BLE001
        return f"error: drive create failed: {type(exc).__name__}"


async def _drive_update_file(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, drive = await _connected_drive(ctx, ctx.org_id or "")
        result = await drive.update_file(args["file_id"], args.get("content", ""), args.get("name", ""), args.get("mime_type", "text/plain"))
        return f"updated Drive file {result.get('id', args['file_id'])}"
    except Exception as exc:  # noqa: BLE001
        return f"error: drive update failed: {type(exc).__name__}"


async def _drive_delete_file(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, drive = await _connected_drive(ctx, ctx.org_id or "")
        await drive.delete_file(args["file_id"])
        return f"deleted Drive file {args['file_id']}"
    except Exception as exc:  # noqa: BLE001
        return f"error: drive delete failed: {type(exc).__name__}"


async def _calendar_list_events(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, cal = await _connected_calendar(ctx, ctx.org_id or "")
    except ValueError as e:
        return f"error: {e}"
    from_ = datetime.fromisoformat(args["from"].replace("Z", "+00:00"))
    to = datetime.fromisoformat(args["to"].replace("Z", "+00:00"))
    events = await cal.list_events(from_=from_, to=to, max_results=args.get("max_results", 25))
    if not events:
        return "no calendar events"
    return "\n".join(f"{e.start_at} {e.title}" for e in events)


async def _calendar_get_event(args: dict[str, Any], ctx: ToolContext) -> str:
    return "error: provider_event_id lookup requires a bound calendar connection"


def register_customer_intelligence_tools() -> None:
    register(
        ToolSpec(
            name="email_list_new",
            description="List new inbound email for a connected account (id, sender, subject).",
            input_schema=EMAIL_LIST_NEW_SCHEMA,
            run=_email_list_new,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="email_get",
            description="Fetch one inbound email by provider_message_id.",
            input_schema=EMAIL_GET_SCHEMA,
            run=_email_get,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="email_create_draft",
            description="Create a text/plain email draft on the connected account.",
            input_schema=EMAIL_CREATE_DRAFT_SCHEMA,
            run=_email_create_draft,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_send",
            description="Send a draft with an explicit idempotency key (duplicate keys no-op).",
            input_schema=EMAIL_SEND_SCHEMA,
            run=_email_send,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(name="drive_list_files", description="List files in the connected Google Drive.", input_schema=DRIVE_LIST_FILES_SCHEMA, run=_drive_list_files, risk_tier=RiskTier.read)
    )
    register(
        ToolSpec(name="drive_get_file", description="Read a text-exportable Google Drive file.", input_schema=DRIVE_GET_FILE_SCHEMA, run=_drive_get_file, risk_tier=RiskTier.read)
    )
    register(
        ToolSpec(name="drive_create_file", description="Create a text file in Google Drive after approval.", input_schema=DRIVE_CREATE_FILE_SCHEMA, run=_drive_create_file, risk_tier=RiskTier.write, requires_approval=True)
    )
    register(
        ToolSpec(name="drive_update_file", description="Update a Google Drive file after approval.", input_schema=DRIVE_UPDATE_FILE_SCHEMA, run=_drive_update_file, risk_tier=RiskTier.write, requires_approval=True)
    )
    register(
        ToolSpec(name="drive_delete_file", description="Delete a Google Drive file after approval.", input_schema=DRIVE_DELETE_FILE_SCHEMA, run=_drive_delete_file, risk_tier=RiskTier.dangerous, requires_approval=True)
    )
    register(
        ToolSpec(
            name="news_search",
            description="Search recent news for a company by query (title/url/snippet).",
            input_schema=NEWS_SEARCH_SCHEMA,
            run=_news_search,
            risk_tier=RiskTier.network,
        )
    )
    register(
        ToolSpec(
            name="company_search",
            description="Search the company identity index by name/alias/industry.",
            input_schema=COMPANY_SEARCH_SCHEMA,
            run=_company_search,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="company_get",
            description="Get one company identity record by company_id.",
            input_schema=COMPANY_GET_SCHEMA,
            run=_company_get,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="calendar_list_events",
            description="List calendar events for the connected account within a time range.",
            input_schema=CALENDAR_LIST_EVENTS_SCHEMA,
            run=_calendar_list_events,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="calendar_get_event",
            description="Get one calendar event by provider_event_id.",
            input_schema=CALENDAR_GET_EVENT_SCHEMA,
            run=_calendar_get_event,
            risk_tier=RiskTier.read,
        )
    )


register_customer_intelligence_tools()