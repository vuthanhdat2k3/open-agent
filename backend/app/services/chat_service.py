from __future__ import annotations

from time import monotonic

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop
from app.db.base import utc_now
from app.models.agent import Agent
from app.models.model import Model
from app.models.session import Session
from app.models.task import Task
from app.schemas.chat import AgentLoopResult, ChatRequest
from app.services.agent_service import AgentService, RuntimeAgent

logger = structlog.get_logger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_agent(
        self, org_id: str, agent_id: str, release_id: str | None = None
    ) -> Agent | RuntimeAgent:
        return await AgentService(self.db).runtime_agent(org_id, agent_id, release_id)

    async def ensure_session(
        self,
        org_id: str,
        request: ChatRequest,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> Session:
        if request.model_id and user_role == "user":
            model = await self.db.scalar(
                select(Model).where(
                    Model.id == request.model_id,
                    Model.org_id == org_id,
                    Model.active.is_(True),
                )
            )
            if model is None:
                raise ValueError("model is not available for this organization")
        selected_agent: Agent | RuntimeAgent | None = None
        if request.model_id:
            # Admin model changes publish a new agent release. Repin an
            # existing session only for that default-model path; a user model
            # choice is a per-request override and must not mutate the release.
            selected_agent = await self._load_agent(org_id, request.agent_id)
        if request.session_id:
            res = await self.db.execute(
                select(Session).where(Session.id == request.session_id, Session.org_id == org_id)
            )
            session = res.scalar_one_or_none()
            if session is not None:
                if session.agent_id != request.agent_id:
                    raise ValueError("session belongs to a different agent")
                if (
                    selected_agent
                    and (user_role != "user" or request.model_id == selected_agent.model_id)
                    and session.agent_release_id != selected_agent.active_release_id
                ):
                    session.agent_release_id = selected_agent.active_release_id
                    await self.db.commit()
                    await self.db.refresh(session)
                return session
        agent = selected_agent or await self._load_agent(org_id, request.agent_id)
        agent = await AgentService(self.db).materialize_system_agent(org_id, agent)
        raw = " ".join(request.message.split())
        title = (raw[:72] + "…") if len(raw) > 72 else raw
        title = title[:1].upper() + title[1:] if title else "New session"
        session = Session(
            org_id=org_id,
            created_by_user_id=user_id,
            agent_id=agent.id,
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
        user_role: str | None = None,
    ) -> tuple[Session, Agent | RuntimeAgent, Task]:
        started_at = monotonic()
        logger.info("chat_latency_phase", phase="prepare_run_start", run_id=run_id)
        session = await self.ensure_session(org_id, request, user_id, user_role)
        logger.info(
            "chat_latency_phase",
            phase="session_ready",
            run_id=run_id,
            elapsed_ms=round((monotonic() - started_at) * 1000, 1),
        )
        agent = await self._load_agent(org_id, request.agent_id, session.agent_release_id)
        logger.info(
            "chat_latency_phase",
            phase="agent_ready",
            run_id=run_id,
            elapsed_ms=round((monotonic() - started_at) * 1000, 1),
        )
        res = await self.db.execute(
            select(Task).where(Task.id == run_id, Task.org_id == org_id)
        )
        task = res.scalar_one_or_none()
        effective_model_id = request.model_id or getattr(agent, "model_id", None)
        if task is not None:
            if task.agent_id != agent.id or task.root_run_id != run_id:
                raise ValueError("chat run belongs to a different agent or organization")
            progress = dict(task.progress or {})
            changed = False
            if "session_id" not in progress:
                progress["session_id"] = session.id
                changed = True
            if "model_id" not in progress:
                progress["model_id"] = effective_model_id
                changed = True
            if changed:
                progress.setdefault("phase", task.status)
                progress.setdefault("last_seq", 0)
                progress.setdefault("updated_at", utc_now().isoformat())
                task.progress = progress
                await self.db.commit()
            logger.info(
                "chat_latency_phase",
                phase="task_ready",
                run_id=run_id,
                elapsed_ms=round((monotonic() - started_at) * 1000, 1),
            )
            return session, agent, task
        task = Task(
            id=run_id,
            org_id=org_id,
            parent_task_id=None,
            root_run_id=run_id,
            agent_id=agent.id,
            agent_release_id=getattr(agent, "active_release_id", None),
            triggered_by_user_id=user_id,
            goal=request.message,
            status="queued",
            progress={
                "session_id": session.id,
                "model_id": effective_model_id,
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

    async def run(
        self,
        org_id: str,
        request: ChatRequest,
        user_id: str | None = None,
        root_run_id: str | None = None,
        current_task_id: str | None = None,
        approval_resume_id: str | None = None,
        user_role: str | None = None,
        prepared: bool = False,
        prepared_agent_release_id: str | None = None,
    ) -> AgentLoopResult:
        if prepared:
            if not request.session_id:
                raise ValueError("prepared chat run requires a session")
            session_id = request.session_id
            agent = await self._load_agent(
                org_id,
                request.agent_id,
                prepared_agent_release_id,
            )
        else:
            session = await self.ensure_session(org_id, request, user_id, user_role)
            session_id = session.id
            agent = await self._load_agent(org_id, request.agent_id, session.agent_release_id)
        return await run_agent_loop(
            agent,
            request.message,
            self.db,
            session_id=session_id,
            current_task_id=current_task_id,
            root_run_id=root_run_id or request.run_id,
            user_id=user_id,
            model_id=request.model_id,
            user_role=user_role,
            approval_resume_id=approval_resume_id,
            timezone_name=request.timezone,
        )
