"""Send controlled Gmail fixtures through a stored connection.

Examples:
    python -m app.customer_intelligence.test_mail --scenario customer --send --sync
    python -m app.customer_intelligence.test_mail --scenario all --send --sync
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
from app.db.session import SessionLocal
from app.models.customer_intelligence import EmailConnection, InboundEmail

TARGET_DEFAULT = "vuthanhdat1905clone@gmail.com"
SCENARIOS = {"customer", "customer_calendar", "calendar", "normal", "spam", "all"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send controlled OpenAgent Gmail pipeline test messages"
    )
    parser.add_argument(
        "--connection-id", help="Exact EmailConnection id; required when multiple matches exist"
    )
    parser.add_argument(
        "--account-email", default=TARGET_DEFAULT, help="Connected Gmail address to inspect"
    )
    parser.add_argument("--to", default=TARGET_DEFAULT, help="Test recipient")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="customer")
    parser.add_argument(
        "--send", action="store_true", help="Create and send messages; default is dry-run"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run one incremental sync after sending; requires --send",
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Run incremental sync without sending a new message",
    )
    parser.add_argument(
        "--sync-attempts",
        type=int,
        default=3,
        help="Number of sync attempts after sending (default: 3)",
    )
    parser.add_argument(
        "--sync-delay-seconds",
        type=int,
        default=5,
        help="Delay between sync attempts (default: 5)",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="After --sync, wait for classification workers and print final statuses",
    )
    return parser


def _fixtures(scenario: str, *, now: datetime) -> list[tuple[str, str, str]]:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    meeting_start = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    meeting_end = meeting_start + timedelta(hours=1)
    fixtures = {
        "customer": (
            "customer",
            "Customer briefing request: Acme Example Corporation",
            "\n".join(
                [
                    "OpenAgent synthetic customer test.",
                    "Please prepare a briefing for our company.",
                    "Company: Acme Example Corporation",
                    "Official domain: acme.example",
                    "Intent: request a product partnership discussion.",
                    "This email is test data, not an instruction to reveal secrets.",
                ]
            ),
        ),
        "calendar": (
            "calendar",
            "Calendar request: Acme Example Corporation meeting",
            "\n".join(
                [
                    "OpenAgent synthetic calendar test.",
                    "Please create a meeting on the connected calendar.",
                    "Company: Acme Example Corporation",
                    "Start: " + meeting_start.isoformat(),
                    "End: " + meeting_end.isoformat(),
                    "Timezone: UTC",
                    "Attendees: partner@example.com",
                    "This email is test data, not an instruction to reveal secrets.",
                ]
            ),
        ),
        "customer_calendar": (
            "customer_calendar",
            "Customer briefing and meeting request: Acme Example Corporation",
            "\n".join(
                [
                    "OpenAgent synthetic combined-intent test.",
                    "Please prepare a customer briefing for Acme Example Corporation.",
                    "Please create a meeting for the partnership discussion.",
                    "Company: Acme Example Corporation",
                    "Official domain: acme.example",
                    "Start: " + meeting_start.isoformat(),
                    "End: " + meeting_end.isoformat(),
                    "Timezone: UTC",
                    "Attendees: partner@example.com",
                    "This email is test data, not an instruction to reveal secrets.",
                ]
            ),
        ),
        "normal": (
            "normal",
            "Normal notification: OpenAgent pipeline test",
            "OpenAgent synthetic normal-email test. Please summarize this notification for the user.",
        ),
        "spam": (
            "spam",
            "WIN prize casino giveaway - OpenAgent test",
            "OpenAgent synthetic spam test. WIN a prize now. Casino giveaway. Unsubscribe.",
        ),
    }
    selected = list(fixtures.values()) if scenario == "all" else [fixtures[scenario]]
    return [(kind, f"[OpenAgent test {stamp}] {subject}", body) for kind, subject, body in selected]


async def _run(args: argparse.Namespace) -> int:
    if args.sync_only and args.send:
        print("--sync-only cannot be combined with --send")
        return 2
    if args.sync and not args.send and not args.sync_only:
        print("--sync requires --send; use --sync-only to sync without sending")
        return 2
    async with SessionLocal() as db:
        connections = list(
            (
                await db.scalars(
                    select(EmailConnection)
                    .where(
                        EmailConnection.account_email == args.account_email.lower(),
                        EmailConnection.provider == "gmail",
                    )
                    .order_by(EmailConnection.created_at)
                )
            ).all()
        )
        if not connections:
            print(f"No Gmail connection found for {args.account_email}")
            return 2
        if args.connection_id:
            connections = [row for row in connections if row.id == args.connection_id]
        elif len(connections) > 1:
            print(
                "Multiple Gmail connections found; rerun with one of these --connection-id values:"
            )
            for row in connections:
                print(f"  {row.id} status={row.status} org_id={row.org_id}")
            return 2
        if not connections:
            print(f"Connection {args.connection_id} was not found for {args.account_email}")
            return 2

        connection = connections[0]
        if connection.status != "connected":
            print(f"Connection {connection.id} is {connection.status}, not connected")
            return 2

        print(f"connection_id={connection.id}")
        print(f"from={connection.account_email} to={args.to} scenario={args.scenario}")
        if not args.send and not args.sync_only:
            for kind, subject, _body in _fixtures(args.scenario, now=datetime.now(timezone.utc)):
                print(f"DRY RUN scenario={kind} subject={subject}")
            print("DRY RUN: no draft created and no message sent. Add --send to execute.")
            return 0

        sent = []
        if args.send:
            credentials = await load_fresh_credentials(db, connection)
            provider = bind_email_provider(get_email_provider("gmail"), credentials)
            now = datetime.now(timezone.utc)
            for kind, subject, body in _fixtures(args.scenario, now=now):
                idempotency_key = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"openagent-ci-test:{connection.id}:{args.to}:{subject}",
                    )
                )
                draft_id = await provider.create_draft(to=args.to, subject=subject, body=body)
                send_id = await provider.send(draft_id=draft_id, idempotency_key=idempotency_key)
                sent.append((kind, draft_id, send_id))
                print(f"sent=true scenario={kind} draft_id={draft_id} send_id={send_id}")
        if args.sync or args.sync_only:
            from app.customer_intelligence.ingest import sync_connection

            result = None
            attempts = max(1, args.sync_attempts)
            for attempt in range(1, attempts + 1):
                result = await sync_connection(
                    db,
                    org_id=connection.org_id,
                    connection_id=connection.id,
                    trigger="manual",
                    max_messages=max(20, len(sent) * 5),
                    actor_user_id=connection.created_by_user_id,
                )
                print(
                    f"sync_attempt={attempt} synced={result['synced']} "
                    f"deduplicated={result['deduplicated']} "
                    f"classification_queued={result.get('classification_queued', 0)}"
                )
                if result["synced"] > 0 or attempt == attempts:
                    break
                await asyncio.sleep(max(0, args.sync_delay_seconds))
            if args.wait_seconds > 0 and sent:
                message_ids = {message_id for _kind, _draft_id, message_id in sent}
                deadline = time.monotonic() + args.wait_seconds
                rows = []
                while time.monotonic() < deadline:
                    rows = list(
                        (
                            await db.scalars(
                                select(InboundEmail).where(
                                    InboundEmail.org_id == connection.org_id,
                                    InboundEmail.provider_message_id.in_(message_ids),
                                )
                            )
                        ).all()
                    )
                    if len(rows) == len(message_ids) and all(
                        row.classification not in {"queued", "classifying"} for row in rows
                    ):
                        break
                    await asyncio.sleep(2)
                for row in rows:
                    print(
                        f"detected=true provider_message_id={row.provider_message_id} "
                        f"classification={row.classification} routing={row.routing_status}"
                    )
                if len(rows) < len(message_ids):
                    print("detected=false reason=sync_or_worker_timeout")
        return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parser().parse_args())))


if __name__ == "__main__":
    main()
