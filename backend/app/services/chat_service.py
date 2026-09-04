from __future__ import annotations

import base64
import os
from time import monotonic
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_loop import run_agent_loop
from app.core.execution_policy import ExecutionPolicy, normalize_execution_policy
from app.core.providers.templates import get_template
from app.db.base import utc_now
from app.models.agent import Agent
from app.models.model import Model
from app.models.provider import Provider
from app.models.session import Session
from app.models.task import Task
from app.schemas.chat import AgentLoopResult, ChatRequest
from app.services.agent_service import AgentService, RuntimeAgent
from app.services.attachment_extract import extract_text, is_extraction_error
from app.services.file_service import FileService

logger = structlog.get_logger(__name__)

_IMAGE_EXTS: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB per image


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
        if user_role == "user":
            # The `user` role only ever consumes the org's orchestrator-kind
            # agent through chat; specialized worker agents are reachable
            # only via the orchestrator's call_agent delegation, never
            # directly. operator/org_admin/platform_admin are unrestricted.
            target_agent = await self._load_agent(org_id, request.agent_id)
            if getattr(target_agent, "kind", "worker") != "orchestrator":
                raise ValueError("this role may only chat with the orchestrator agent")
            selected_agent = target_agent
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
        execution_policy = normalize_execution_policy(request.execution_policy)
        if execution_policy is ExecutionPolicy.full_access and user_role not in {
            "user",
            "operator",
            "org_admin",
            "platform_admin",
        }:
            raise ValueError("full-access execution policy is not available for this role")
        session = Session(
            org_id=org_id,
            created_by_user_id=user_id,
            agent_id=agent.id,
            agent_release_id=getattr(agent, "active_release_id", None),
            title=title,
            execution_policy=execution_policy.value,
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
            execution_principal={
                "principal_type": "human" if user_id else "system",
                "principal_id": user_id or "openagent:internal-runtime",
                "user_id": user_id,
                "role": user_role,
            },
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

    async def _model_supports_vision(self, org_id: str, model_id: str | None) -> bool:
        if not model_id:
            return False
        res = await self.db.execute(
            select(Model, Provider.template_key)
            .join(Provider, Model.provider_id == Provider.id, isouter=True)
            .where(Model.id == model_id, Model.org_id == org_id)
        )
        row = res.first()
        if not row:
            return False
        model, template_key = row
        if model.supports_vision is not None:
            return bool(model.supports_vision)
        template = get_template(template_key or "")
        return bool(template.supports_vision) if template else False

    async def _inline_attachments(
        self,
        org_id: str,
        message: str,
        attachment_ids: list[str],
        user_id: str | None,
        supports_vision: bool = False,
    ) -> tuple[str, list[dict[str, str]], list[dict[str, str]], list[str]]:
        """Read each attachment's content and append it to the prompt for
        this turn. Read-only against S3 — never calls the RAG ingest path.

        When supports_vision is True and the attachment is an image, retains
        the base64-encoded image instead of forcing OCR via Docling.
        """
        files = FileService(self.db)
        blocks = []
        attachments_meta: list[dict[str, str]] = []
        images: list[dict[str, str]] = []
        warnings: list[str] = []
        for file_id in attachment_ids:
            result = await files.download(org_id, file_id, owner_user_id=user_id)
            if result is None:
                continue
            data, record = result
            ext = os.path.splitext(record.original_name)[1].lower()
            if supports_vision and ext in _IMAGE_EXTS:
                if len(data) > MAX_IMAGE_BYTES:
                    warn = (
                        f"[could not read '{record.original_name}': "
                        f"image size exceeds 5MB limit]"
                    )
                    warnings.append(warn.strip("[]"))
                    blocks.append(f"--- Attached file: {record.original_name} ---\n{warn}")
                    attachments_meta.append(
                        {"id": file_id, "name": record.original_name, "error": warn}
                    )
                else:
                    b64_data = base64.b64encode(data).decode("utf-8")
                    images.append(
                        {
                            "mime_type": _IMAGE_EXTS[ext],
                            "data_b64": b64_data,
                            "name": record.original_name,
                        }
                    )
                    attachments_meta.append({"id": file_id, "name": record.original_name})
            elif ext in _IMAGE_EXTS:
                # Image attachment with a non-vision model: do not attempt text extraction or docling.
                warn_msg = (
                    f"[could not process '{record.original_name}': "
                    f"Current model does not support visual image inputs (Vision). "
                    f"Please inform the user and ask them to switch to a Vision-capable model.]"
                )
                blocks.append(f"--- Attached image: {record.original_name} ---\n{warn_msg}")
                warnings.append(
                    f"'{record.original_name}': Mô hình hiện tại không hỗ trợ đọc ảnh (Vision). Vui lòng chuyển sang mô hình có hỗ trợ Vision."
                )
                attachments_meta.append(
                    {
                        "id": file_id,
                        "name": record.original_name,
                        "error": "Model does not support vision",
                    }
                )
            else:
                text = await extract_text(data, record.original_name)
                blocks.append(f"--- Attached file: {record.original_name} ---\n{text}")
                meta_item = {"id": file_id, "name": record.original_name}
                if is_extraction_error(text):
                    warnings.append(text.strip("[]"))
                    meta_item["error"] = text
                attachments_meta.append(meta_item)

        if not blocks:
            return message, attachments_meta, images, warnings
        return message + "\n\n" + "\n\n".join(blocks), attachments_meta, images, warnings

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
            session_res = await self.db.execute(
                select(Session).where(Session.id == request.session_id, Session.org_id == org_id)
            )
            session = session_res.scalar_one_or_none()
            if session is None:
                raise ValueError("chat session not found")
            if request.execution_policy:
                new_policy = normalize_execution_policy(request.execution_policy)
                if new_policy is ExecutionPolicy.full_access and user_role not in {
                    "user",
                    "operator",
                    "org_admin",
                    "platform_admin",
                }:
                    raise ValueError("full-access execution policy is not available for this role")
                session.execution_policy = new_policy.value
                await self.db.commit()
                await self.db.refresh(session)
            session_id = session.id
            agent = await self._load_agent(
                org_id,
                request.agent_id,
                prepared_agent_release_id or session.agent_release_id,
            )
        else:
            session = await self.ensure_session(org_id, request, user_id, user_role)
            session_id = session.id
            agent = await self._load_agent(org_id, request.agent_id, session.agent_release_id)

        effective_model_id = request.model_id or getattr(agent, "model_id", None)
        supports_vision = await self._model_supports_vision(org_id, effective_model_id)

        message = request.message
        message_meta: dict[str, object] | None = None
        attachment_warnings: list[str] = []
        message_images: list[dict[str, str]] = []
        if request.attachment_ids:
            message, attachments_meta, message_images, attachment_warnings = (
                await self._inline_attachments(
                    org_id,
                    message,
                    request.attachment_ids,
                    user_id,
                    supports_vision=supports_vision,
                )
            )
            if attachments_meta:
                message_meta = {"attachments": attachments_meta}

        message_payload: str | dict[str, Any] = (
            {"text": message, "images": message_images} if message_images else message
        )

        return await run_agent_loop(
            agent,
            message_payload,
            self.db,
            session_id=session_id,
            current_task_id=current_task_id,
            root_run_id=root_run_id or request.run_id,
            user_id=user_id,
            model_id=request.model_id,
            user_role=user_role,
            approval_resume_id=approval_resume_id,
            timezone_name=request.timezone,
            execution_policy=normalize_execution_policy(session.execution_policy),
            display_message=request.message,
            message_meta=message_meta,
            attachment_warnings=attachment_warnings,
        )

