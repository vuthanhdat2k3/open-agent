from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config import get_settings
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.customer_intelligence.contracts import (
    CALENDAR_CREATE_EVENT_SCHEMA,
    CALENDAR_DELETE_EVENT_SCHEMA,
    CALENDAR_GET_EVENT_SCHEMA,
    CALENDAR_LIST_EVENTS_SCHEMA,
    CALENDAR_UPDATE_EVENT_SCHEMA,
    COMPANY_GET_SCHEMA,
    COMPANY_SEARCH_SCHEMA,
    DRIVE_CREATE_FILE_SCHEMA,
    DRIVE_DELETE_FILE_SCHEMA,
    DRIVE_GET_FILE_SCHEMA,
    DRIVE_LIST_FILES_SCHEMA,
    DRIVE_UPDATE_FILE_SCHEMA,
    EMAIL_CREATE_DRAFT_SCHEMA,
    EMAIL_FORWARD_SCHEMA,
    EMAIL_GET_SCHEMA,
    EMAIL_LABEL_SCHEMA,
    EMAIL_LABELS_SCHEMA,
    EMAIL_LIST_NEW_SCHEMA,
    EMAIL_REPLY_SCHEMA,
    EMAIL_SEARCH_SCHEMA,
    EMAIL_SEND_SCHEMA,
    EMAIL_STATE_SCHEMA,
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


async def _email_search(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
        messages = await provider.search(query=args["query"], max_results=args.get("max_results", 20))
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"
    if not messages:
        return "No matching email"
    return "\n".join(f"{m.provider_message_id} | {m.sender_email} | {m.subject}" for m in messages)


async def _email_modify(args: dict[str, Any], ctx: ToolContext, *, add: list[str] | None = None, remove: list[str] | None = None) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
        message_id = await provider.modify(provider_message_id=args["provider_message_id"], add_label_ids=add, remove_label_ids=remove)
        return f"email updated successfully: {message_id}"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


async def _email_mark_read(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, remove=["UNREAD"])


async def _email_mark_unread(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, add=["UNREAD"])


async def _email_star(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, add=["STARRED"])


async def _email_unstar(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, remove=["STARRED"])


async def _email_archive(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, remove=["INBOX"])


async def _email_trash(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
        return f"email moved to trash: {await provider.trash(args['provider_message_id'])}"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


async def _email_restore(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
        return f"email restored: {await provider.untrash(args['provider_message_id'])}"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


async def _email_list_labels(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
        labels = await provider.list_labels()
        return "\n".join(f"{x.get('id')} | {x.get('name')}" for x in labels) or "No labels"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


async def _email_apply_label(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, add=args["label_ids"])


async def _email_remove_label(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _email_modify(args, ctx, remove=args["label_ids"])


async def _email_reply(args: dict[str, Any], ctx: ToolContext) -> str:
    try:
        msg = await (await _connected_provider(ctx, ctx.org_id or ""))[1].get_message(args["provider_message_id"])
        return await _email_create_draft({"to": msg.sender_email, "subject": f"Re: {msg.subject}", "body": args["body"], "in_reply_to": args["provider_message_id"]}, ctx)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


async def _email_forward(args: dict[str, Any], ctx: ToolContext) -> str:
    try:
        msg = await (await _connected_provider(ctx, ctx.org_id or ""))[1].get_message(args["provider_message_id"])
        body = args.get("body") or "\n\n---------- Forwarded message ----------\n" + msg.body_text
        return await _email_create_draft({"to": args["to"], "subject": f"Fwd: {msg.subject}", "body": body}, ctx)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


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
    try:
        _, provider = await _connected_provider(ctx, ctx.org_id or "")
    except ValueError as e:
        return f"error: {e}"
    try:
        send_id = await provider.send(
            draft_id=args["draft_id"],
            idempotency_key=args["idempotency_key"],
        )
    except Exception as e:  # noqa: BLE001 - normalize provider details.
        return f"error: {e}"
    return f"email sent successfully (send_id: {send_id})"


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
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, cal = await _connected_calendar(ctx, ctx.org_id or "")
        event = await cal.get_event(args["provider_event_id"])
        return "event not found" if event is None else f"{event.start_at} {event.title} | {event.provider_event_id}"
    except Exception as exc:  # noqa: BLE001
        return f"error: calendar get failed: {type(exc).__name__}"


async def _calendar_create_event(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, cal = await _connected_calendar(ctx, ctx.org_id or "")
        result = await cal.create_event(
            summary=args["summary"], start=args["start"], end=args["end"],
            description=args.get("description", ""), location=args.get("location", ""), attendees=args.get("attendees", []),
        )
        return f"created calendar event {result.get('provider_event_id', '')}"
    except Exception as exc:  # noqa: BLE001
        return f"error: calendar create failed: {type(exc).__name__}"


async def _calendar_update_event(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, cal = await _connected_calendar(ctx, ctx.org_id or "")
        updates = {key: value for key, value in args.items() if key != "provider_event_id"}
        result = await cal.update_event(args["provider_event_id"], **updates)
        return f"updated calendar event {result.get('provider_event_id', args['provider_event_id'])}"
    except Exception as exc:  # noqa: BLE001
        return f"error: calendar update failed: {type(exc).__name__}"


async def _calendar_delete_event(args: dict[str, Any], ctx: ToolContext) -> str:
    if not _enabled():
        return "error: customer intelligence is disabled"
    try:
        _, cal = await _connected_calendar(ctx, ctx.org_id or "")
        await cal.delete_event(args["provider_event_id"])
        return f"deleted calendar event {args['provider_event_id']}"
    except Exception as exc:  # noqa: BLE001
        return f"error: calendar delete failed: {type(exc).__name__}"


def register_customer_intelligence_tools() -> None:
    register(
        ToolSpec(
            name="email_list_new",
            description=(
                "List recent messages in the connected Gmail inbox and return message ID, "
                "sender, and subject. Use email_search instead for dates, people, subjects, "
                "attachments, or other filters."
            ),
            input_schema=EMAIL_LIST_NEW_SCHEMA,
            run=_email_list_new,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="email_get",
            description=(
                "Read one Gmail message by the provider_message_id returned from "
                "email_list_new or email_search."
            ),
            input_schema=EMAIL_GET_SCHEMA,
            run=_email_get,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="email_search",
            description=(
                "Search the connected Gmail account. Convert the user's request to Gmail query "
                "syntax, including date operators such as newer_than:1d or after:YYYY/MM/DD "
                "before:YYYY/MM/DD. Returns message ID, sender, and subject."
            ),
            input_schema=EMAIL_SEARCH_SCHEMA,
            run=_email_search,
            risk_tier=RiskTier.read,
        )
    )
    for name, description, runner in (
        ("email_mark_read", "Mark an email as read.", _email_mark_read),
        ("email_mark_unread", "Mark an email as unread.", _email_mark_unread),
        ("email_star", "Star an email.", _email_star),
        ("email_unstar", "Remove the star from an email.", _email_unstar),
        ("email_archive", "Archive an email by removing it from Inbox.", _email_archive),
    ):
        register(
            ToolSpec(
                name=name,
                description=f"{description} Requires a provider_message_id returned by an email tool.",
                input_schema=EMAIL_STATE_SCHEMA,
                run=runner,
                risk_tier=RiskTier.write,
                requires_approval=True,
            )
        )
    register(
        ToolSpec(
            name="email_trash",
            description=(
                "Move one Gmail message to Trash by provider_message_id; never permanently delete it."
            ),
            input_schema=EMAIL_STATE_SCHEMA,
            run=_email_trash,
            risk_tier=RiskTier.dangerous,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_restore",
            description="Restore one Gmail message from Trash by provider_message_id.",
            input_schema=EMAIL_STATE_SCHEMA,
            run=_email_restore,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_list_labels",
            description="List Gmail label IDs and display names for the connected account.",
            input_schema=EMAIL_LABELS_SCHEMA,
            run=_email_list_labels,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="email_apply_label",
            description="Apply Gmail label IDs to one message identified by provider_message_id.",
            input_schema=EMAIL_LABEL_SCHEMA,
            run=_email_apply_label,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_remove_label",
            description="Remove Gmail label IDs from one message identified by provider_message_id.",
            input_schema=EMAIL_LABEL_SCHEMA,
            run=_email_remove_label,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_reply",
            description="Create a reply draft for a Gmail message ID; this does not send it.",
            input_schema=EMAIL_REPLY_SCHEMA,
            run=_email_reply,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_forward",
            description="Create a forward draft from a Gmail message ID; this does not send it.",
            input_schema=EMAIL_FORWARD_SCHEMA,
            run=_email_forward,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_create_draft",
            description=(
                "Create a text/plain email draft on the connected account and return its draft_id. "
                "Use email_send separately only when the draft should be sent."
            ),
            input_schema=EMAIL_CREATE_DRAFT_SCHEMA,
            run=_email_create_draft,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="email_send",
            description=(
                "Send an existing draft_id with an explicit idempotency key; duplicate keys no-op. "
                "Create the draft first when no draft_id is available."
            ),
            input_schema=EMAIL_SEND_SCHEMA,
            run=_email_send,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="drive_list_files",
            description=(
                "List recent non-trashed Google Drive files, optionally filtering by a "
                "case-insensitive filename substring. Returns file IDs and metadata, not content."
            ),
            input_schema=DRIVE_LIST_FILES_SCHEMA,
            run=_drive_list_files,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="drive_get_file",
            description=(
                "Read text content from one Google Drive file ID returned by drive_list_files. "
                "Google-native documents are exported as plain text."
            ),
            input_schema=DRIVE_GET_FILE_SCHEMA,
            run=_drive_get_file,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="drive_create_file",
            description="Create a Google Drive text file with a name, content, and optional parent folder ID.",
            input_schema=DRIVE_CREATE_FILE_SCHEMA,
            run=_drive_create_file,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="drive_update_file",
            description="Update content or name for one Google Drive file ID.",
            input_schema=DRIVE_UPDATE_FILE_SCHEMA,
            run=_drive_update_file,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="drive_delete_file",
            description="Delete one Google Drive file by file ID.",
            input_schema=DRIVE_DELETE_FILE_SCHEMA,
            run=_drive_delete_file,
            risk_tier=RiskTier.dangerous,
            requires_approval=True,
        )
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
            description=(
                "List connected Google Calendar events in an ISO-8601 time range. Resolve relative "
                "dates such as today or tomorrow and include timezone offsets before calling."
            ),
            input_schema=CALENDAR_LIST_EVENTS_SCHEMA,
            run=_calendar_list_events,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="calendar_get_event",
            description="Get one Google Calendar event by provider_event_id returned by a calendar tool.",
            input_schema=CALENDAR_GET_EVENT_SCHEMA,
            run=_calendar_get_event,
            risk_tier=RiskTier.read,
        )
    )
    register(
        ToolSpec(
            name="calendar_create_event",
            description=(
                "Create a Google Calendar event with ISO-8601 start/end timestamps including "
                "timezone offsets."
            ),
            input_schema=CALENDAR_CREATE_EVENT_SCHEMA,
            run=_calendar_create_event,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="calendar_update_event",
            description=(
                "Update fields on one Google Calendar provider_event_id; any replacement times "
                "must be ISO-8601 with timezone offsets."
            ),
            input_schema=CALENDAR_UPDATE_EVENT_SCHEMA,
            run=_calendar_update_event,
            risk_tier=RiskTier.write,
            requires_approval=True,
        )
    )
    register(
        ToolSpec(
            name="calendar_delete_event",
            description="Delete one Google Calendar event by provider_event_id.",
            input_schema=CALENDAR_DELETE_EVENT_SCHEMA,
            run=_calendar_delete_event,
            risk_tier=RiskTier.dangerous,
            requires_approval=True,
        )
    )


register_customer_intelligence_tools()
