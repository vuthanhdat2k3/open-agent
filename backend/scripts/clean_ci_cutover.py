"""One-time checkpointed cutover for one Gmail connection."""

from __future__ import annotations

import argparse
import asyncio

from app.customer_intelligence.cutover import clean_cutover
from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.email import bind_email_provider, get_email_provider
from app.db.session import SessionLocal
from app.models.customer_intelligence import EmailConnection


async def main(args: argparse.Namespace) -> None:
    if not args.confirm:
        raise SystemExit("Refusing to run without --confirm; this deletes derived CI data.")
    async with SessionLocal() as db:
        connection = await db.get(EmailConnection, args.connection_id)
        if connection is None or connection.org_id != args.org_id:
            raise SystemExit("Connection not found in the requested organization")
        if connection.status != "connected" or not connection.credentials_enc:
            raise SystemExit("Connection must be connected and have credentials")
        # Stop sync workers before reading the barrier checkpoint. Push events
        # remain durable and will retry after the connection is restored.
        connection.status = "cutover"
        await db.commit()
        try:
            credentials = await load_fresh_credentials(db, connection)
            provider = bind_email_provider(get_email_provider(connection.provider), credentials)
            checkpoint = await provider.get_history_checkpoint()
            idempotency_key = args.idempotency_key or f"cutover:{connection.id}:{checkpoint}"
            result = await clean_cutover(
                db,
                org_id=args.org_id,
                connection_id=connection.id,
                cutover_history_id=checkpoint,
                idempotency_key=idempotency_key,
                actor=args.actor,
            )
        finally:
            await db.rollback()
            await db.refresh(connection)
            connection.status = "connected"
            await db.commit()
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean cutover for one Gmail connection")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--idempotency-key")
    parser.add_argument("--actor", required=True)
    asyncio.run(main(parser.parse_args()))
