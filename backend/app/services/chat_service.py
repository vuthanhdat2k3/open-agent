from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop, stream_agent
from app.db.base import utc_now
from app.models.agent import Agent
from app.models.session import Session
from app.models.task import Task
from app.schemas.chat import AgentLoopResult, ChatRequest
from app.services.agent_service import AgentService, RuntimeAgent


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_agent(
        self, org_id: str, agent_id: str, release_id: str | None = None
    ) -> Agent | RuntimeAgent:
        return await AgentService(self.db).runtime_agent(org_id, agent_id, release_id)

    async def ensure_session(
        self, org_id: str, request: ChatRequest, user_id: str | None = None
    ) -> Session:
        if request.session_id:
            res = await self.db.execute(
                select(Session).where(Session.id == request.session_id, Session.org_id == org_id)
            )
            session = res.scalar_one_or_none()
            if session is not None:
                if session.agent_id != request.agent_id:
                    raise ValueError("session belongs to a different agent")
                return session
        agent = await self._load_agent(org_id, request.agent_id)
        raw = " ".join(request.message.split())
        title = (raw[:72] + "…") if len(raw) > 72 else raw
        title = title[:1].upper() + title[1:] if title else "New session"
        session = Session(
            org_id=org_id,
            created_by_user_id=user_id,
            agent_id=request.agent_id,
            agent_release_id=getattr(agent, "active_release_id", None),
            title=title,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def prepare_run(
        self,
        org_id: str,
        request: ChatRequest,
        run_id: str,
        user_id: str | None = None,
    ) -> tuple[Session, Agent | RuntimeAgent, Task]:
        session = await self.ensure_session(org_id, request, user_id)
        agent = await self._load_agent(org_id, request.agent_id, session.agent_release_id)
        res = await self.db.execute(
            select(Task).where(Task.id == run_id, Task.org_id == org_id)
        )
        task = res.scalar_one_or_none()
        if task is not None:
            if task.agent_id != agent.id or task.root_run_id != run_id:
                raise ValueError("chat run belongs to a different agent or organization")
            if not task.progress:
                task.progress = {
                    "session_id": session.id,
                    "phase": task.status,
                    "last_seq": 0,
                    "updated_at": utc_now().isoformat(),
                }
                await self.db.commit()
            return session, agent, task
        task = Task(
            id=run_id,
            org_id=org_id,
            parent_task_id=None,
            root_run_id=run_id,
            agent_id=agent.id,
            agent_release_id=getattr(agent, "active_release_id", None),
            goal=request.message,
            status="queued",
            progress={
                "session_id": session.id,
                "phase": "queued",
                "last_seq": 0,
                "updated_at": utc_now().isoformat(),
            },
            depth=0,
            created_at=utc_now(),
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return session, agent, task

    async def stream(
        self,
        org_id: str,
        request: ChatRequest,
        user_id: str | None = None,
        root_run_id: str | None = None,
        current_task_id: str | None = None,
    ) -> AsyncIterator[dict]:
        session = await self.ensure_session(org_id, request, user_id)
        agent = await self._load_agent(org_id, request.agent_id, session.agent_release_id)
        async for ev in stream_agent(
            agent,
            request.message,
            self.db,
            session.id,
            root_run_id=root_run_id or request.run_id,
            current_task_id=current_task_id,
            user_id=user_id,
        ):
            yield ev

    async def run(
        self,
        org_id: str,
        request: ChatRequest,
        user_id: str | None = None,
        root_run_id: str | None = None,
        current_task_id: str | None = None,
    ) -> AgentLoopResult:
        session = await self.ensure_session(org_id, request, user_id)
        agent = await self._load_agent(org_id, request.agent_id, session.agent_release_id)
        return await run_agent_loop(
            agent,
            request.message,
            self.db,
            session_id=session.id,
            current_task_id=current_task_id,
            root_run_id=root_run_id or request.run_id,
            user_id=user_id,
        )
