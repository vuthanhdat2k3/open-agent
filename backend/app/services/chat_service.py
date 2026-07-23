from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop, stream_agent
from app.models.agent import Agent
from app.models.session import Session
from app.schemas.chat import AgentLoopResult, ChatRequest


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_agent(self, org_id: str, agent_id: str) -> Agent:
        res = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
        agent = res.scalar_one_or_none()
        if agent is None:
            raise ValueError("agent not found")
        return agent

    async def ensure_session(
        self, org_id: str, request: ChatRequest, user_id: str | None = None
    ) -> Session:
        if request.session_id:
            res = await self.db.execute(
                select(Session).where(Session.id == request.session_id, Session.org_id == org_id)
            )
            s = res.scalar_one_or_none()
            if s is not None:
                return s
        await self._load_agent(org_id, request.agent_id)
        raw = " ".join(request.message.split())
        title = (raw[:72] + "…") if len(raw) > 72 else raw
        title = title[:1].upper() + title[1:] if title else "New session"
        s = Session(
            org_id=org_id, created_by_user_id=user_id, agent_id=request.agent_id, title=title
        )
        self.db.add(s)
        await self.db.commit()
        await self.db.refresh(s)
        return s

    async def stream(
        self, org_id: str, request: ChatRequest, user_id: str | None = None
    ) -> AsyncIterator[dict]:
        agent = await self._load_agent(org_id, request.agent_id)
        session = await self.ensure_session(org_id, request, user_id)
        async for ev in stream_agent(agent, request.message, self.db, session.id):
            yield ev

    async def run(
        self, org_id: str, request: ChatRequest, user_id: str | None = None
    ) -> AgentLoopResult:
        agent = await self._load_agent(org_id, request.agent_id)
        session = await self.ensure_session(org_id, request, user_id)
        return await run_agent_loop(agent, request.message, self.db, session_id=session.id)
