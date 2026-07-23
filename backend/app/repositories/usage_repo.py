from sqlalchemy import func, select

from app.models.usage import UsageEvent
from app.repositories.base import BaseRepository


class UsageRepository(BaseRepository[UsageEvent]):
    def __init__(self, db):
        super().__init__(UsageEvent, db)

    async def summary(self, org_id: str) -> list[dict]:
        res = await self.db.execute(
            select(
                UsageEvent.agent_name,
                UsageEvent.model_name,
                func.sum(UsageEvent.input_tokens).label("input_tokens"),
                func.sum(UsageEvent.output_tokens).label("output_tokens"),
                func.sum(UsageEvent.cost_usd).label("cost_usd"),
                func.sum(UsageEvent.latency_ms).label("latency_ms"),
                func.count(UsageEvent.id).label("calls"),
            )
            .where(UsageEvent.org_id == org_id)
            .group_by(UsageEvent.agent_name, UsageEvent.model_name)
        )
        rows = res.all()
        return [
            {
                "agent_name": r.agent_name,
                "model_name": r.model_name,
                "input_tokens": int(r.input_tokens or 0),
                "output_tokens": int(r.output_tokens or 0),
                "cost_usd": round(float(r.cost_usd or 0), 6),
                "latency_ms": int(r.latency_ms or 0),
                "calls": int(r.calls or 0),
            }
            for r in rows
        ]

    async def recent(self, org_id: str, limit: int = 50) -> list[UsageEvent]:
        res = await self.db.execute(
            select(UsageEvent)
            .where(UsageEvent.org_id == org_id)
            .order_by(UsageEvent.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())
