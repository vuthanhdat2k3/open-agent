from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import PrincipalContext
from app.core.authz.scope import scope_to_owner
from app.core.execution_policy import ExecutionPolicy, normalize_execution_policy
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.memory import SessionMemory
from app.models.message import Message
import logging
from app.core import session_log as slog
from app.core.memory.tiers import compact_tiered_memory
from app.models.agent import Agent
from app.models.model import Model
from app.models.provider import Provider

logger = logging.getLogger(__name__)

from app.models.session import Session
from app.models.session_event import SessionEvent
from app.models.user import User
from app.models.workspace import WorkspaceArtifact
from app.schemas.chat import ChatMessageOut, SessionOut, SessionUpdate

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
)


@router.get("", response_model=list[SessionOut], dependencies=[Depends(require_permission("sessions:read"))])
async def list_sessions(
    org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    stmt = scope_to_owner(
        select(Session, User)
        .outerjoin(User, Session.created_by_user_id == User.id)
        .where(Session.org_id == org_id),
        db,
        Session.created_by_user_id,
    ).order_by(Session.updated_at.desc())
    res = await db.execute(stmt)
    sessions: list[SessionOut] = []
    for session, user in res.all():
        sessions.append(
            SessionOut(
                id=session.id,
                agent_id=session.agent_id,
                execution_policy=session.execution_policy,
                title=session.title,
                created_by_user_id=session.created_by_user_id,
                creator_email=user.email if user else None,
                creator_name=user.display_name if user else None,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
        )
    return sessions


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut], dependencies=[Depends(require_permission("sessions:read"))])
async def list_messages(
    session_id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    session_stmt = scope_to_owner(
        select(Session).where(Session.id == session_id, Session.org_id == org_id),
        db,
        Session.created_by_user_id,
    )
    if await db.scalar(session_stmt) is None:
        raise HTTPException(404, "session not found")
    stmt = scope_to_owner(
        select(Message)
        .join(Session, Session.id == Message.session_id)
        .where(Message.session_id == session_id, Message.org_id == org_id),
        db,
        Session.created_by_user_id,
    ).order_by(Message.position)
    res = await db.execute(stmt)
    messages = list(res.scalars().all())

    # Query all artifacts for this session
    art_stmt = (
        select(WorkspaceArtifact)
        .where(
            WorkspaceArtifact.org_id == org_id,
            or_(
                WorkspaceArtifact.session_id == session_id,
                WorkspaceArtifact.root_run_id == session_id,
            ),
        )
        .order_by(WorkspaceArtifact.created_at.asc())
    )
    art_res = await db.execute(art_stmt)
    artifacts = list(art_res.scalars().all())
    if not artifacts:
        return messages

    assistant_indices = [i for i, m in enumerate(messages) if m.role == "assistant"]
    if not assistant_indices:
        return messages

    def _to_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    # Map each artifact to the assistant message of the turn that created or updated it
    art_by_msg_idx: dict[int, list[dict[str, Any]]] = {}

    for art in artifacts:
        a_created = _to_utc(art.created_at)
        a_updated = _to_utc(art.updated_at) or a_created
        a_latest = max(a_created, a_updated) if (a_created and a_updated) else (a_created or a_updated)

        matched_idx = None
        for pos, a_idx in enumerate(assistant_indices):
            m_dt = _to_utc(messages[a_idx].created_at)
            prev_m_dt = _to_utc(messages[assistant_indices[pos - 1]].created_at) if pos > 0 else None

            # Check if artifact was created or modified during this turn:
            # - After previous turn's assistant message (or from start if pos == 0)
            # - Created on or before this assistant message (+ 2s grace window)
            is_after_prev = prev_m_dt is None or (a_latest is not None and a_latest >= prev_m_dt)
            is_before_current = m_dt is not None and a_created is not None and (
                a_created <= (m_dt + timedelta(seconds=2))
            )

            if is_after_prev and is_before_current:
                matched_idx = a_idx
                break

        if matched_idx is None:
            # Fallback: assign to the earliest assistant message created after artifact creation
            for a_idx in assistant_indices:
                m_dt = _to_utc(messages[a_idx].created_at)
                if m_dt and a_created and m_dt >= a_created:
                    matched_idx = a_idx
                    break

        if matched_idx is None:
            matched_idx = assistant_indices[-1]

        art_entry = {
            "id": art.id,
            "path": art.path,
            "filename": Path(art.path).name,
            "content_type": art.content_type,
            "size": art.size,
            "download_url": f"/api/workspace/artifacts/{art.id}/download",
            "content_url": f"/api/workspace/artifacts/{art.id}/download?inline=true",
            "source_tool": art.source_tool,
        }
        art_by_msg_idx.setdefault(matched_idx, []).append(art_entry)

    out: list[ChatMessageOut] = []
    for idx, m in enumerate(messages):
        meta = dict(m.meta or {})
        if m.role == "assistant":
            # Assign scoped artifacts belonging to this turn
            turn_artifacts = art_by_msg_idx.get(idx, [])
            if turn_artifacts or "artifacts" in meta:
                meta["artifacts"] = turn_artifacts
        out.append(
            ChatMessageOut(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                meta=meta,
                position=m.position,
                created_at=m.created_at,
            )
        )
    return out


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("sessions:write")),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        scope_to_owner(
            select(Session).where(Session.id == session_id, Session.org_id == org_id),
            db,
            Session.created_by_user_id,
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "session not found")
    if payload.execution_policy is not None:
        new_policy = normalize_execution_policy(payload.execution_policy)
        user_role = (
            authz.role.value if hasattr(authz.role, "value") else str(authz.role)
        ) if authz and authz.role else getattr(user, "role", None)
        if new_policy is ExecutionPolicy.full_access and user_role not in {
            "user",
            "operator",
            "org_admin",
            "platform_admin",
        }:
            raise HTTPException(403, "full-access execution policy is not available for this role")
        s.execution_policy = new_policy.value
    if payload.title is not None:
        s.title = payload.title
    await db.commit()
    await db.refresh(s)
    return s


@router.delete("/{session_id}", dependencies=[Depends(require_permission("sessions:delete"))])
async def delete_session(
    session_id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    res = await db.execute(
        scope_to_owner(
            select(Session).where(Session.id == session_id, Session.org_id == org_id),
            db,
            Session.created_by_user_id,
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "session not found")
    await db.execute(
        delete(SessionMemory).where(
            SessionMemory.session_id == session_id, SessionMemory.org_id == org_id
        )
    )
    await db.execute(
        delete(Message).where(Message.session_id == session_id, Message.org_id == org_id)
    )
    await db.execute(
        delete(SessionEvent).where(
            SessionEvent.session_id == session_id, SessionEvent.org_id == org_id
        )
    )
    await db.delete(s)
    await db.commit()
    return {"ok": True, "id": session_id}


@router.post("/{session_id}/clear", dependencies=[Depends(require_permission("sessions:write"))])
async def clear_session_messages(
    session_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        scope_to_owner(
            select(Session).where(Session.id == session_id, Session.org_id == org_id),
            db,
            Session.created_by_user_id,
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "session not found")

    await db.execute(
        delete(SessionMemory).where(
            SessionMemory.session_id == session_id, SessionMemory.org_id == org_id
        )
    )
    await db.execute(
        delete(Message).where(Message.session_id == session_id, Message.org_id == org_id)
    )
    await db.execute(
        delete(SessionEvent).where(
            SessionEvent.session_id == session_id, SessionEvent.org_id == org_id
        )
    )
    await db.commit()
    return {"ok": True, "session_id": session_id, "message": "Session history cleared successfully"}


@router.post("/{session_id}/compact", dependencies=[Depends(require_permission("sessions:write"))])
async def compact_session(
    session_id: str,
    org_id: str = Depends(get_current_org_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        scope_to_owner(
            select(Session).where(Session.id == session_id, Session.org_id == org_id),
            db,
            Session.created_by_user_id,
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "session not found")

    # Fetch existing messages
    msg_res = await db.execute(
        select(Message).where(Message.session_id == session_id, Message.org_id == org_id).order_by(Message.position)
    )
    messages = list(msg_res.scalars().all())

    # Fetch existing session events
    events = await slog.load_events(db, session_id)

    # Need at least some conversation history to warrant compaction
    if len(messages) <= 2 and len(events) <= 4:
        return {
            "ok": True,
            "compacted": False,
            "message": "Ngữ cảnh phiên còn quá ngắn, chưa cần nén.",
            "summary": None,
        }

    # Resolve agent and model/provider
    agent = None
    if s.agent_id:
        agent_res = await db.execute(
            select(Agent).where(Agent.id == s.agent_id, Agent.org_id == org_id)
        )
        agent = agent_res.scalar_one_or_none()

    model = None
    provider = None
    agent_model_id = getattr(agent, 'model_id', None)
    if agent and agent_model_id:
        model_res = await db.execute(
            select(Model).where(Model.id == agent_model_id)
        )
        model = model_res.scalar_one_or_none()
        if model:
            prov_res = await db.execute(
                select(Provider).where(Provider.id == model.provider_id)
            )
            provider = prov_res.scalar_one_or_none()

    # Fallback to active model in org if needed
    if not model or not provider:
        fallback_model_res = await db.execute(
            select(Model).where(Model.org_id == org_id, Model.active == True).limit(1)  # noqa: E712
        )
        model = fallback_model_res.scalar_one_or_none()
        if model:
            prov_res = await db.execute(
                select(Provider).where(Provider.id == model.provider_id)
            )
            provider = prov_res.scalar_one_or_none()

    warm_summary = ""
    hot_window = 2  # Keep the last 2 messages uncompacted

    if model and provider:
        try:
            tiered = await compact_tiered_memory(
                session_id=session_id,
                db=db,
                agent_model=model,
                provider=provider,
                hot_window=hot_window,
                agent_id=agent.id if agent else None,
                org_id=org_id,
                created_by_user_id=user.id,
            )
            warm_summary = tiered.get("warm") or tiered.get("combined") or ""
        except Exception as exc:
            logger.warning("compact_tiered_memory failed, falling back to extractive summary: %s", exc)

    if not warm_summary:
        # Fallback extractive summary when LLM summarization is unavailable
        transcript_parts = []
        older = messages[:-hot_window] if len(messages) > hot_window else messages
        for m in older:
            content_preview = (m.content or "").strip()
            if len(content_preview) > 150:
                content_preview = content_preview[:150] + "..."
            transcript_parts.append(f"- {m.role}: {content_preview}")
        joined_transcript = "\n".join(transcript_parts)
        warm_summary = f"Bản tóm tắt lược trích các trao đổi trước đó:\n{joined_transcript}"

    # 1. Update Session Event Log (Shadow old events)
    if events and len(events) > 2:
        events_to_shadow = events[:-2]
        shadow_seqs = [e.seq for e in events_to_shadow]
        start_seq = shadow_seqs[0]
        end_seq = shadow_seqs[-1]
        await slog.append_event(
            db,
            session_id=session_id,
            org_id=org_id,
            type_=slog.COMPACTION_SUMMARY,
            data={
                "content": f"[Tóm tắt ngữ cảnh trước đó]:\n{warm_summary}",
                "source_seqs": shadow_seqs,
                "surface_op": {
                    "op": "replace",
                    "start_seq": start_seq,
                    "end_seq": end_seq,
                },
            },
        )

    # 2. Update Message table for UI hydration
    if len(messages) > hot_window:
        hot_messages = messages[-hot_window:]
        older_messages = messages[:-hot_window]
        older_ids = [m.id for m in older_messages]

        # Delete older messages
        await db.execute(
            delete(Message).where(Message.id.in_(older_ids))
        )

        # Insert a summary assistant message representing the compacted history
        compaction_msg = Message(
            org_id=org_id,
            created_by_user_id=user.id,
            session_id=session_id,
            role="assistant",
            content=f"🧹 **Đã nén ngữ cảnh phiên hội thoại**:\n\n{warm_summary}",
            meta={
                "is_compaction": True,
                "compacted_at": datetime.now(timezone.utc).isoformat(),
                "compacted_messages_count": len(older_messages),
            },
            position=0,
        )
        db.add(compaction_msg)

        # Shift positions of hot messages
        for idx, m in enumerate(hot_messages, start=1):
            m.position = idx

    await db.commit()

    return {
        "ok": True,
        "compacted": True,
        "message": "Đã nén ngữ cảnh hội thoại thành công.",
        "summary": warm_summary,
    }
