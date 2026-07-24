from __future__ import annotations

from datetime import datetime, timezone

from redis.asyncio import Redis, from_url
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.quota.redis_backend import RedisQuotaBackend
from app.models.agent import Agent
from app.models.files import UploadedFile
from app.models.organization import Organization
from app.models.organization_quota import OrganizationQuota
from app.models.usage import UsageEvent
from app.models.workflow import Workflow


def default_organization_quota(org_id: str) -> OrganizationQuota:
    settings = get_settings()
    return OrganizationQuota(
        org_id=org_id,
        requests_per_minute=settings.quota_requests_per_minute,
        agent_runs_per_minute=settings.quota_agent_runs_per_minute,
        max_concurrent_runs=settings.quota_max_concurrent_runs,
        monthly_cost_usd=settings.quota_monthly_cost_usd,
        enforcement_mode="enforce",
    )


async def invalidate_monthly_cost_cache(org_id: str) -> None:
    settings = get_settings()
    redis = from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        await redis.delete(QuotaService._cost_cache_key(org_id))
    except Exception:  # noqa: BLE001 - usage persistence must not depend on cache
        pass
    finally:
        await redis.aclose()


class QuotaService:
    def __init__(self, db: AsyncSession, redis: Redis | None = None) -> None:
        self.db = db
        self.redis = redis
        self.settings = get_settings()

    async def get(self, org_id: str) -> OrganizationQuota | None:
        quota = await self.db.get(OrganizationQuota, org_id)
        if quota is not None:
            return quota
        if await self.db.get(Organization, org_id) is None:
            return None
        quota = default_organization_quota(org_id)
        self.db.add(quota)
        await self.db.commit()
        await self.db.refresh(quota)
        return quota

    async def get_for_update(self, org_id: str) -> OrganizationQuota | None:
        result = await self.db.execute(
            select(OrganizationQuota)
            .where(OrganizationQuota.org_id == org_id)
            .with_for_update()
        )
        quota = result.scalar_one_or_none()
        return quota if quota is not None else await self.get(org_id)

    async def update(
        self, org_id: str, values: dict, user_id: str | None
    ) -> OrganizationQuota:
        quota = await self.get(org_id)
        if quota is None:
            raise ValueError("organization not found")
        for field, value in values.items():
            setattr(quota, field, value)
        quota.updated_by_user_id = user_id
        await self.db.commit()
        await self.db.refresh(quota)
        if self.redis is not None:
            try:
                await self.redis.delete(self._cost_cache_key(org_id))
            except Exception:  # noqa: BLE001 - mutation already persisted
                pass
        return quota

    async def monthly_cost(self, org_id: str) -> float:
        key = self._cost_cache_key(org_id)
        if self.redis is not None:
            try:
                cached = await self.redis.get(key)
                if cached is not None:
                    return float(cached)
            except Exception:  # noqa: BLE001 - durable database fallback
                pass
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1)
        value = await self.db.scalar(
            select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0)).where(
                UsageEvent.org_id == org_id,
                UsageEvent.created_at >= month_start,
            )
        )
        cost = float(value or 0.0)
        if self.redis is not None:
            try:
                await self.redis.set(
                    key, str(cost), ex=self.settings.quota_usage_cache_seconds
                )
            except Exception:  # noqa: BLE001 - cache is optional for reads
                pass
        return cost

    async def usage(self, org_id: str) -> dict:
        quota = await self.get(org_id)
        if quota is None:
            raise ValueError("organization not found")
        agents = await self._count(Agent, org_id)
        workflows = await self._count(Workflow, org_id)
        storage = await self.db.scalar(
            select(func.coalesce(func.sum(UploadedFile.size), 0)).where(
                UploadedFile.org_id == org_id
            )
        )
        active = 0
        if self.redis is not None:
            try:
                active = await RedisQuotaBackend(self.redis).active_leases(org_id)
            except Exception:  # noqa: BLE001 - read paths fail open
                pass
        now = datetime.now(timezone.utc)
        return {
            "org_id": org_id,
            "month": f"{now.year:04d}-{now.month:02d}",
            "monthly_cost_usd": await self.monthly_cost(org_id),
            "monthly_cost_limit_usd": quota.monthly_cost_usd,
            "agents": agents,
            "agent_limit": quota.max_agents,
            "workflows": workflows,
            "workflow_limit": quota.max_workflows,
            "storage_bytes": int(storage or 0),
            "storage_limit_bytes": quota.max_storage_bytes,
            "active_run_leases": active,
            "concurrent_run_limit": quota.max_concurrent_runs,
        }

    async def resource_count(self, org_id: str, resource: str) -> int:
        models = {"agents": Agent, "workflows": Workflow}
        return await self._count(models[resource], org_id)

    async def storage_bytes(self, org_id: str) -> int:
        value = await self.db.scalar(
            select(func.coalesce(func.sum(UploadedFile.size), 0)).where(
                UploadedFile.org_id == org_id
            )
        )
        return int(value or 0)

    async def _count(self, model, org_id: str) -> int:
        value = await self.db.scalar(
            select(func.count(model.id)).where(model.org_id == org_id)
        )
        return int(value or 0)

    @staticmethod
    def _cost_cache_key(org_id: str) -> str:
        return f"openagent:quota:monthly-cost:{org_id}"
