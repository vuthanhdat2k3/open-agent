from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop, stream_agent
from app.models.agent import Agent
from app.models.session import Session
from app.schemas.chat import AgentLoopResult, ChatRequest


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_agent(self, agent_id: str) -> Agent:
        res = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        agent = res.scalar_one_or_none()
        if agent is None:
            raise ValueError("agent not found")
        return agent

    async def ensure_session(self, request: ChatRequest) -> Session:
        if request.session_id:
            res = await self.db.execute(
                select(Session).where(Session.id == request.session_id)
            )
            s = res.scalar_one_or_none()
            if s is not None:
                return s
        await self._load_agent(request.agent_id)
        raw = " ".join(request.message.split())  # collapse whitespace/newlines
        title = (raw[:72] + "…") if len(raw) > 72 else raw
        title = title[:1].upper() + title[1:] if title else "New session"
        s = Session(agent_id=request.agent_id, title=title)
        self.db.add(s)
        await self.db.commit()
        await self.db.refresh(s)
        return s

    async def stream(
        self, request: ChatRequest
    ) -> AsyncIterator[dict]:
        agent = await self._load_agent(request.agent_id)
        session = await self.ensure_session(request)
        async for ev in stream_agent(agent, request.message, self.db, session.id):
            yield ev

    async def run(self, request: ChatRequest) -> AgentLoopResult:
        agent = await self._load_agent(request.agent_id)
        session = await self.ensure_session(request)
        return await run_agent_loop(agent, request.message, self.db, session_id=session.id)
