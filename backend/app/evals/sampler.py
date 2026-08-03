"""Turn production traces into proposed regression cases.

Every incident the guardrails caught is a test nobody wrote yet. This reads
the M13 audit trail, finds runs worth freezing, and proposes them as
evaluation cases.

The hard rule: a proposal is **never** graded until a human approves it.
The sampler can see that a run went wrong; it cannot know what the right
answer would have been. It proposes, a person decides.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.guardrails.secrets import scan_and_redact
from app.db.base import utc_now
from app.models.audit_log import AuditLog
from app.models.evaluation import EvaluationCase
from app.models.message import Message
from app.models.sampling_policy import SamplingPolicy
from app.models.session import Session

# Audit action -> the policy reason that selects it.
SAMPLE_REASON_BY_ACTION: dict[str, str] = {
    "guardrail.injection_flagged": "guardrail_injection_flagged",
    "guardrail.secret_redacted": "guardrail_secret_redacted",
    "guardrail.risk_tier_denied": "run_failed",
    "guardrail.budget_exceeded": "max_iterations_reached",
}

# Proposals are never graded, so they carry no dataset version. The real
# version is assigned at approval time, which is also when the suite's
# dataset_version is bumped.
UNVERSIONED = 0


async def find_candidates(
    db: AsyncSession,
    policy: SamplingPolicy,
    *,
    since_hours: int = 24,
) -> list[tuple[str, str]]:
    """Return ``[(session_id, reason)]`` for runs worth proposing.

    Only actions the policy opted into are considered, and each run is
    proposed at most once even if it tripped several guardrails.
    """
    wanted_actions = [
        action
        for action, reason in SAMPLE_REASON_BY_ACTION.items()
        if reason in (policy.reasons or [])
    ]
    if not wanted_actions:
        return []

    since = utc_now() - timedelta(hours=since_hours)
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.org_id == policy.org_id,
            AuditLog.action.in_(wanted_actions),
            AuditLog.created_at >= since,
        )
        .order_by(AuditLog.created_at)
    )

    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for row in result.scalars().all():
        run_id = (row.metadata_ or {}).get("run_id")
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        candidates.append((run_id, SAMPLE_REASON_BY_ACTION[row.action]))
    return candidates


async def _already_proposed(db: AsyncSession, suite_id: str, run_id: str) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(EvaluationCase)
        .where(
            EvaluationCase.suite_id == suite_id,
            EvaluationCase.source_run_ref == run_id,
        )
    )
    return bool(result.scalar_one())


async def _proposed_today(db: AsyncSession, suite_id: str) -> int:
    since = utc_now() - timedelta(hours=24)
    result = await db.execute(
        select(func.count())
        .select_from(EvaluationCase)
        .where(
            EvaluationCase.suite_id == suite_id,
            EvaluationCase.source == "sampled",
            EvaluationCase.created_at >= since,
        )
    )
    return int(result.scalar_one())


async def _first_user_message(db: AsyncSession, session_id: str) -> str | None:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.role == "user")
        .order_by(Message.position)
        .limit(1)
    )
    message = result.scalars().first()
    return message.content if message else None


async def propose_cases(db: AsyncSession, policy: SamplingPolicy) -> list[EvaluationCase]:
    """Create unapproved cases for runs matching ``policy``.

    Returns the proposals created. Nothing becomes gradeable as a result:
    the cases are unapproved and carry no dataset version, so suite runs
    ignore them until a reviewer accepts them.
    """
    if not policy.enabled:
        return []

    budget = policy.max_per_day - await _proposed_today(db, policy.suite_id)
    if budget <= 0:
        return []

    proposals: list[EvaluationCase] = []
    for run_id, reason in await find_candidates(db, policy):
        if len(proposals) >= budget:
            break
        if await _already_proposed(db, policy.suite_id, run_id):
            continue

        session = (
            await db.execute(
                select(Session).where(
                    Session.id == run_id,
                    Session.org_id == policy.org_id,
                    Session.agent_id == policy.agent_id,
                )
            )
        ).scalar_one_or_none()
        if session is None:
            continue

        user_input = await _first_user_message(db, run_id)
        if not user_input:
            continue

        # The dataset must never become a place where production secrets
        # accumulate, even though the transcript was already redacted once.
        safe_input, _ = scan_and_redact(user_input)

        ordinal = int(
            (
                await db.execute(
                    select(func.coalesce(func.max(EvaluationCase.ordinal), 0)).where(
                        EvaluationCase.suite_id == policy.suite_id
                    )
                )
            ).scalar_one()
        )
        case = EvaluationCase(
            org_id=policy.org_id,
            suite_id=policy.suite_id,
            input=safe_input,
            # No expected_output: only a human knows what should have
            # happened, and a guessed expectation is worse than none.
            expected_output=None,
            ordinal=ordinal + 1,
            added_in_version=UNVERSIONED,
            source="sampled",
            source_run_ref=run_id,
            sampled_reason=reason,
            approved=False,
        )
        db.add(case)
        proposals.append(case)

    if proposals:
        await db.commit()
        for case in proposals:
            await db.refresh(case)
    return proposals
