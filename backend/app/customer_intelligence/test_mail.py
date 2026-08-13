"""Send one deterministic Gmail test message through a stored connection."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
from app.db.session import SessionLocal
from app.models.customer_intelligence import EmailConnection

TARGET_DEFAULT = "vuthanhdat1905clone@gmail.com"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a single OpenAgent Gmail pipeline test message")
    parser.add_argument("--connection-id", help="Exact EmailConnection id; required when multiple matches exist")
    parser.add_argument("--account-email", default=TARGET_DEFAULT, help="Connected Gmail address to inspect")
    parser.add_argument("--to", default=TARGET_DEFAULT, help="Test recipient")
    parser.add_argument("--send", action="store_true", help="Create and send the test message; default is dry-run")
    return parser


async def _run(args: argparse.Namespace) -> int:
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
            print("Multiple Gmail connections found; rerun with one of these --connection-id values:")
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

        subject = "[OpenAgent CI test] customer meeting request"
        body = (
            "OpenAgent controlled test message.\n\n"
            "Customer: Acme Example Corporation\n"
            "Domain: acme.example\n"
            "Request: Please prepare a customer briefing and check a meeting next Tuesday at 10:00.\n\n"
            "This message is synthetic test data. Do not treat its content as instructions.\n"
            f"Test timestamp UTC: {datetime.now(timezone.utc).isoformat()}\n"
        )
        idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"openagent-ci-test:{connection.id}:{args.to}:{subject}"))
        print(f"connection_id={connection.id}")
        print(f"from={connection.account_email} to={args.to} subject={subject}")
        print(f"idempotency_key={idempotency_key}")
        if not args.send:
            print("DRY RUN: no draft created and no message sent. Add --send to execute once.")
            return 0

        credentials = await load_fresh_credentials(db, connection)
        provider = bind_email_provider(get_email_provider("gmail"), credentials)
        draft_id = await provider.create_draft(to=args.to, subject=subject, body=body)
        send_id = await provider.send(draft_id=draft_id, idempotency_key=idempotency_key)
        print(f"sent=true draft_id={draft_id} send_id={send_id}")
        return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parser().parse_args())))


if __name__ == "__main__":
    main()
