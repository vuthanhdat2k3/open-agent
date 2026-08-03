from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.a2a.card import generate_agent_card
from app.models.agent import Agent


async def get_exposed_agent_card(
    db: AsyncSession, org_id: str, base_url: str = ""
) -> dict[str, Any]:
    """Retrieves exposed agents for org_id and builds Agent Card json."""
    stmt = select(Agent).where(Agent.org_id == org_id, Agent.a2a_exposed.is_(True))
    result = await db.execute(stmt)
    agents = list(result.scalars().all())
    return generate_agent_card(agents, base_url)


async def validate_a2a_agent_access(db: AsyncSession, org_id: str, agent_id: str) -> Agent:
    """Validates that agent exists, belongs to org, and is exposed via A2A."""
    stmt = select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    if not agent.a2a_exposed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent '{agent.name}' is not exposed for A2A communication",
        )

    return agent
