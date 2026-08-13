"""One-time clean cutover for agent email classification."""

from __future__ import annotations

import argparse
import asyncio

from app.customer_intelligence.cutover import clean_cutover
from app.db.session import SessionLocal


async def main(args: argparse.Namespace) -> None:
    if not args.confirm:
        raise SystemExit("Refusing to run without --confirm; this deletes derived CI data.")
    if args.org_id and args.connection_id:
        raise SystemExit("Use only one scope: --org-id or --connection-id")
    async with SessionLocal() as db:
        result = await clean_cutover(
            db, org_id=args.org_id, connection_id=args.connection_id, actor=args.actor
        )
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean cutover for agent email classification")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--org-id")
    parser.add_argument("--connection-id")
    parser.add_argument("--actor", default="operator")
    asyncio.run(main(parser.parse_args()))
