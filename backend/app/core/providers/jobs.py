from __future__ import annotations

from typing import Any

import structlog
from arq import Retry
from sqlalchemy import select, update

from app.core.providers.templates import get_template
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.models.provider import Provider
from app.services.model_discovery_service import ModelDiscoveryService
from app.services.provider_service import ProviderService, _legacy_template

logger = structlog.get_logger(__name__)
_MAX_DISCOVERY_TRIES = 3


async def run_provider_discovery(
    ctx: dict[str, Any], provider_id: str, discovery_generation: int
) -> None:
    """Discover a provider catalog for one immutable credential generation.

    The job carries no credential. It reloads the encrypted provider row in the
    worker process and refuses to apply results after a newer update wins.
    """
    async with SessionLocal() as db:
        provider = await db.scalar(select(Provider).where(Provider.id == provider_id))
        if provider is None or provider.discovery_generation != discovery_generation:
            return

        claimed = await db.execute(
            update(Provider)
            .where(
                Provider.id == provider_id,
                Provider.discovery_generation == discovery_generation,
                Provider.discovery_status == "pending",
            )
            .values(discovery_status="running", discovery_error=None)
        )
        if claimed.rowcount != 1:
            return
        await db.commit()

        try:
            provider = await db.scalar(select(Provider).where(Provider.id == provider_id))
            if provider is None or provider.discovery_generation != discovery_generation:
                return
            service = ProviderService(db)
            driver = service._driver_for(provider)
            template = get_template(provider.template_key or "")
            result = await ModelDiscoveryService.probe(
                driver, template or _legacy_template()
            )

            provider = await db.scalar(
                select(Provider).where(Provider.id == provider_id).with_for_update()
            )
            if provider is None or provider.discovery_generation != discovery_generation:
                await db.rollback()
                return
            await service._persist_discovery(
                provider, template, result, now=utc_now()
            )
            await db.commit()
            await logger.ainfo(
                "provider_discovery_finished",
                provider_id=provider_id,
                discovery_generation=discovery_generation,
                discovery_status=provider.discovery_status,
                models_discovered=provider.models_discovered,
            )
        except Exception as exc:  # noqa: BLE001 - retry provider connectivity failures.
            await db.rollback()
            provider = await db.scalar(
                select(Provider).where(Provider.id == provider_id).with_for_update()
            )
            if provider is None or provider.discovery_generation != discovery_generation:
                return
            job_try = int(ctx.get("job_try", 1))
            if job_try < _MAX_DISCOVERY_TRIES:
                provider.discovery_status = "pending"
                provider.discovery_error = f"discovery retry scheduled: {type(exc).__name__}"
                await db.commit()
                raise Retry(defer=5 * (2 ** (job_try - 1))) from exc
            provider.discovery_status = "failed"
            provider.discovery_error = f"discovery job error: {type(exc).__name__}"
            provider.status = "error"
            await db.commit()
            await logger.aerror(
                "provider_discovery_failed",
                provider_id=provider_id,
                discovery_generation=discovery_generation,
                error_type=type(exc).__name__,
            )
