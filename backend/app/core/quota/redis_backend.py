from __future__ import annotations

import uuid
from dataclasses import dataclass

from redis.asyncio import Redis

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local redis_time = redis.call('TIME')
local now = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local member = ARGV[3]
local observe = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local before = redis.call('ZCARD', key)
local allowed = 0
if before < limit then allowed = 1 end
if allowed == 1 or observe == 1 then
  redis.call('ZADD', key, now, member)
end
redis.call('PEXPIRE', key, window)
local count = redis.call('ZCARD', key)
local first = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local reset_ms = window
if first[2] then reset_ms = math.max(0, tonumber(first[2]) + window - now) end
return {allowed, count, math.ceil(reset_ms / 1000)}
"""

LEASE_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local redis_time = redis.call('TIME')
local now = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
local expires = now + tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local token = ARGV[3]
local observe = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
local before = redis.call('ZCARD', key)
local allowed = 0
if before < limit then allowed = 1 end
if allowed == 1 or observe == 1 then
  redis.call('ZADD', key, expires, token)
end
redis.call('PEXPIRE', key, math.max(1000, expires - now))
return {allowed, redis.call('ZCARD', key)}
"""


@dataclass(frozen=True)
class WindowDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    observed_count: int


@dataclass(frozen=True)
class LeaseDecision:
    allowed: bool
    token: str | None
    active: int
    limit: int


class RedisQuotaBackend:
    def __init__(self, redis: Redis, prefix: str = "openagent:quota") -> None:
        self.redis = redis
        self.prefix = prefix

    async def sliding_window(
        self,
        org_id: str,
        limit_type: str,
        limit: int,
        *,
        window_seconds: int = 60,
        observe: bool = False,
    ) -> WindowDecision:
        result = await self.redis.eval(
            SLIDING_WINDOW_SCRIPT,
            1,
            f"{self.prefix}:window:{limit_type}:{org_id}",
            window_seconds * 1000,
            limit,
            uuid.uuid4().hex,
            int(observe),
        )
        allowed, count, reset = (int(value) for value in result)
        return WindowDecision(
            allowed=bool(allowed),
            limit=limit,
            remaining=max(0, limit - count),
            reset_seconds=max(1, reset),
            observed_count=count,
        )

    async def acquire_lease(
        self,
        org_id: str,
        limit: int,
        *,
        ttl_seconds: int,
        observe: bool = False,
    ) -> LeaseDecision:
        token = uuid.uuid4().hex
        result = await self.redis.eval(
            LEASE_ACQUIRE_SCRIPT,
            1,
            f"{self.prefix}:leases:{org_id}",
            ttl_seconds * 1000,
            limit,
            token,
            int(observe),
        )
        allowed, active = (int(value) for value in result)
        accepted = bool(allowed) or observe
        return LeaseDecision(
            allowed=bool(allowed),
            token=token if accepted else None,
            active=active,
            limit=limit,
        )

    async def release_lease(self, org_id: str, token: str) -> None:
        await self.redis.zrem(f"{self.prefix}:leases:{org_id}", token)

    async def active_leases(self, org_id: str) -> int:
        key = f"{self.prefix}:leases:{org_id}"
        seconds, microseconds = await self.redis.time()
        now_ms = int(seconds) * 1000 + int(microseconds) // 1000
        await self.redis.zremrangebyscore(key, "-inf", now_ms)
        return int(await self.redis.zcard(key))
