from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator

import structlog
from fastapi import Depends, HTTPException, Request, Response
from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.audit import log_action
from app.core.observability.chat_timing import mark_chat_phase
from app.core.observability.metrics import (
    quota_active_run_leases,
    quota_admission_total,
    quota_backend_failures_total,
)
from app.core.quota.redis_backend import RedisQuotaBackend
from app.db.session import get_db
from app.dependencies import get_current_org_id, get_current_user
from app.models.user import User
from app.services.quota_service import QuotaService

logger = structlog.get_logger(__name__)


def _tenant_hash(org_id: str) -> str:
    return hashlib.sha256(org_id.encode()).hexdigest()[:12]


def _rate_headers(decision) -> dict[str, str]:
    return {
        "RateLimit-Limit": str(decision.limit),
        "RateLimit-Remaining": str(decision.remaining),
        "RateLimit-Reset": str(decision.reset_seconds),
    }


async def _audit_quota_denied(
    db: AsyncSession, org_id: str, limit_type: str, enforcement_mode: str
) -> None:
    """Record an admission refusal.

    A rejected run is an operator-visible event: without it, "the agent
    stopped responding" is indistinguishable from a crash in the audit
    trail. Committed immediately because the caller raises straight after.
    """
    await log_action(
        db,
        org_id=org_id,
        action="quota.denied",
        resource_type="organization",
        resource_id=org_id,
        metadata={"limit_type": limit_type, "enforcement_mode": enforcement_mode},
    )


async def _redis_client() -> AsyncGenerator[Redis, None]:
    client = from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        yield client
    finally:
        await client.aclose()


async def _authenticated_org_id(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> str:
    return await get_current_org_id(request, db)


async def enforce_request_quota(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(_redis_client),
    org_id: str = Depends(_authenticated_org_id),
) -> None:
    quota = await QuotaService(db, redis).get(org_id)
    request.state.org_quota = quota
    mark_chat_phase(request, "request_quota_loaded")
    if quota is None or redis is None:
        return
    observe = quota.enforcement_mode == "observe"
    try:
        decision = await RedisQuotaBackend(redis).sliding_window(
            org_id,
            "requests",
            quota.requests_per_minute,
            observe=observe,
        )
        mark_chat_phase(request, "request_quota_checked")
    except Exception as exc:  # noqa: BLE001
        quota_backend_failures_total.labels("request_window").inc()
        await logger.awarning(
            "quota_backend_failure",
            operation="request_window",
            tenant_hash=_tenant_hash(org_id),
            request_id=getattr(request.state, "request_id", None),
            error=str(exc),
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not observe:
            raise HTTPException(503, "quota service unavailable") from exc
        return
    for name, value in _rate_headers(decision).items():
        response.headers[name] = value
    request.state.rate_limit_headers = _rate_headers(decision)
    metric_decision = (
        "allow" if decision.allowed else "observe" if observe else "reject"
    )
    quota_admission_total.labels("requests", metric_decision).inc()
    if not decision.allowed and not observe:
        await _audit_quota_denied(db, org_id, "requests", "enforce")
        raise HTTPException(
            429,
            "request rate limit exceeded",
            headers={
                **_rate_headers(decision),
                "Retry-After": str(decision.reset_seconds),
            },
        )


async def agent_run_admission(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(_redis_client),
    org_id: str = Depends(_authenticated_org_id),
) -> AsyncGenerator[None, None]:
    quota = getattr(request.state, "org_quota", None)
    if quota is None:
        quota = await QuotaService(db, redis).get(org_id)
        request.state.org_quota = quota
    if quota is None:
        raise HTTPException(404, "organization not found")
    mark_chat_phase(request, "agent_quota_start")
    if redis is None:
        yield
        return
    observe = quota.enforcement_mode == "observe"
    backend = RedisQuotaBackend(redis)
    token: str | None = None
    try:
        rate = await backend.sliding_window(
            org_id,
            "agent-runs",
            quota.agent_runs_per_minute,
            observe=observe,
        )
        mark_chat_phase(request, "agent_rate_checked")
        if not rate.allowed:
            quota_admission_total.labels(
                "agent_runs", "observe" if observe else "reject"
            ).inc()
            if not observe:
                await _audit_quota_denied(db, org_id, "agent_runs", "enforce")
                raise HTTPException(
                    429,
                    "agent run rate limit exceeded",
                    headers={
                        **_rate_headers(rate),
                        "Retry-After": str(rate.reset_seconds),
                    },
                )
        else:
            quota_admission_total.labels("agent_runs", "allow").inc()

        cost = await QuotaService(db, redis).monthly_cost(org_id)
        mark_chat_phase(request, "monthly_cost_checked")
        if cost >= quota.monthly_cost_usd:
            quota_admission_total.labels(
                "monthly_cost", "observe" if observe else "reject"
            ).inc()
            if not observe:
                await _audit_quota_denied(db, org_id, "monthly_cost", "enforce")
                raise HTTPException(429, "monthly cost limit reached")
        else:
            quota_admission_total.labels("monthly_cost", "allow").inc()

        lease = await backend.acquire_lease(
            org_id,
            quota.max_concurrent_runs,
            ttl_seconds=get_settings().quota_run_lease_ttl_seconds,
            observe=observe,
        )
        mark_chat_phase(request, "concurrency_lease_checked")
        quota_active_run_leases.set(lease.active)
        if not lease.allowed:
            quota_admission_total.labels(
                "concurrent_runs", "observe" if observe else "reject"
            ).inc()
            if not observe:
                await _audit_quota_denied(db, org_id, "concurrent_runs", "enforce")
                raise HTTPException(
                    429,
                    "concurrent agent run limit reached",
                    headers={"Retry-After": "1"},
                )
        else:
            quota_admission_total.labels("concurrent_runs", "allow").inc()
        token = lease.token
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        quota_backend_failures_total.labels("run_admission").inc()
        await logger.aerror(
            "quota_backend_failure",
            operation="run_admission",
            tenant_hash=_tenant_hash(org_id),
            request_id=getattr(request.state, "request_id", None),
            error=str(exc),
        )
        if observe:
            pass
        else:
            raise HTTPException(503, "quota service unavailable") from exc
    try:
        yield
    finally:
        if token:
            try:
                await backend.release_lease(org_id, token)
            except Exception:  # noqa: BLE001
                quota_backend_failures_total.labels("lease_release").inc()


def enforce_resource_quota(resource: str):
    if resource not in {"agents", "workflows"}:
        raise ValueError(f"unsupported quota resource: {resource}")

    async def _dependency(
        db: AsyncSession = Depends(get_db),
        org_id: str = Depends(get_current_org_id),
    ) -> None:
        service = QuotaService(db)
        quota = await service.get_for_update(org_id)
        if quota is None:
            raise HTTPException(404, "organization not found")
        limit = getattr(quota, f"max_{resource}")
        if limit is None:
            return
        count = await service.resource_count(org_id, resource)
        if count >= limit:
            quota_admission_total.labels(
                resource,
                "observe" if quota.enforcement_mode == "observe" else "reject",
            ).inc()
            if quota.enforcement_mode == "enforce":
                raise HTTPException(429, f"{resource} quota reached")
        else:
            quota_admission_total.labels(resource, "allow").inc()

    return _dependency
