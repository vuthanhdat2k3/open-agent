"""M15 — trace sampler and the human approval gate.

The invariant this file exists to protect: a sampled case is a *proposal*.
It must never be graded, and must never move the dataset version, until a
person has confirmed what the right answer was.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.evals.sampler import find_candidates, propose_cases
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.evaluation import EvaluationCase, EvaluationSuite
from app.models.message import Message
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.sampling_policy import DEFAULT_SAMPLING_REASONS, SamplingPolicy
from app.models.session import Session
from app.services.evaluation_service import EvaluationService

# Synthetic, non-functional — shaped like a key so the redactor fires.
SECRET_VALUE = "sk-samplertestsecret0123456789abcdef"


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(db: AsyncSession) -> tuple[Agent, EvaluationSuite, SamplingPolicy]:
    org = Organization(name="Sampler Org", slug="sampler-org")
    db.add(org)
    await db.commit()
    await db.refresh(org)

    provider = Provider(
        org_id=org.id, name="OpenAI", key="openai", base_url="http://x", api_key="k"
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    model = Model(
        org_id=org.id, provider_id=provider.id, name="gpt-4o-mini", display_name="GPT-4o mini"
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    agent = Agent(org_id=org.id, name="sampled", model_id=model.id, tools=[])
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    suite = EvaluationSuite(org_id=org.id, agent_id=agent.id, name="Regressions")
    db.add(suite)
    await db.commit()
    await db.refresh(suite)

    policy = SamplingPolicy(
        org_id=org.id,
        agent_id=agent.id,
        suite_id=suite.id,
        enabled=True,
        reasons=DEFAULT_SAMPLING_REASONS,
        max_per_day=10,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return agent, suite, policy


async def _incident(
    db: AsyncSession,
    agent: Agent,
    *,
    user_text: str = "why did that fail?",
    action: str = "guardrail.injection_flagged",
) -> str:
    """Create a run that tripped a guardrail, as M13 would have recorded it."""
    session = Session(org_id=agent.org_id, agent_id=agent.id, title="incident")
    db.add(session)
    await db.commit()
    await db.refresh(session)

    db.add(
        Message(
            org_id=agent.org_id,
            session_id=session.id,
            role="user",
            content=user_text,
            position=0,
        )
    )
    db.add(
        AuditLog(
            org_id=agent.org_id,
            action=action,
            resource_type="tool",
            resource_id="web_fetch",
            metadata_={"source": "web_fetch", "run_id": session.id},
        )
    )
    await db.commit()
    return session.id


# --------------------------------------------------------------------------- #
# Candidate selection
# --------------------------------------------------------------------------- #
async def test_finds_runs_that_tripped_a_guardrail(session_factory) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        run_id = await _incident(db, agent)

        candidates = await find_candidates(db, policy)

    assert candidates == [(run_id, "guardrail_injection_flagged")]


async def test_policy_reasons_filter_what_is_considered(session_factory) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        await _incident(db, agent)
        policy.reasons = ["run_failed"]  # injection no longer of interest
        await db.commit()

        candidates = await find_candidates(db, policy)

    assert candidates == []


async def test_one_run_is_proposed_once_even_with_several_guardrail_hits(
    session_factory,
) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        run_id = await _incident(db, agent)
        db.add(
            AuditLog(
                org_id=agent.org_id,
                action="guardrail.secret_redacted",
                resource_type="tool",
                resource_id="web_fetch",
                metadata_={"count": 1, "kinds": ["openai_key"], "run_id": run_id},
            )
        )
        await db.commit()

        candidates = await find_candidates(db, policy)

    assert len(candidates) == 1


# --------------------------------------------------------------------------- #
# Proposal is never gradeable
# --------------------------------------------------------------------------- #
async def test_proposal_is_unapproved_and_does_not_move_dataset_version(
    session_factory,
) -> None:
    async with session_factory() as db:
        agent, suite, policy = await _seed(db)
        version_before = suite.dataset_version
        await _incident(db, agent)

        proposals = await propose_cases(db, policy)
        await db.refresh(suite)

        graded = await EvaluationService(db).list_cases(agent.org_id, suite.id)
        pending = await EvaluationService(db).list_proposed_cases(agent.org_id, suite.id)

    assert len(proposals) == 1
    assert proposals[0].approved is False
    assert proposals[0].source == "sampled"
    assert proposals[0].sampled_reason == "guardrail_injection_flagged"
    assert proposals[0].expected_output is None, "the sampler must not invent an answer"
    assert suite.dataset_version == version_before, "a proposal is not a dataset change"
    assert graded == [], "an unreviewed proposal must never be graded"
    assert len(pending) == 1


async def test_disabled_policy_proposes_nothing(session_factory) -> None:
    """Copying production traffic into a dataset is opt-in."""
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        policy.enabled = False
        await db.commit()
        await _incident(db, agent)

        proposals = await propose_cases(db, policy)

    assert proposals == []


async def test_sampled_input_is_redacted(session_factory) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        await _incident(db, agent, user_text=f"my key is {SECRET_VALUE} please check")

        proposals = await propose_cases(db, policy)

    assert proposals
    assert SECRET_VALUE not in proposals[0].input


async def test_same_run_is_never_proposed_twice(session_factory) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        await _incident(db, agent)

        first = await propose_cases(db, policy)
        second = await propose_cases(db, policy)

    assert len(first) == 1
    assert second == []


async def test_daily_cap_is_respected(session_factory) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        policy.max_per_day = 2
        await db.commit()
        for _ in range(4):
            await _incident(db, agent)

        proposals = await propose_cases(db, policy)

    assert len(proposals) == 2, "max_per_day must bound dataset growth"


# --------------------------------------------------------------------------- #
# Approval
# --------------------------------------------------------------------------- #
async def test_approval_requires_a_stated_expectation(session_factory) -> None:
    """Only a human knows the right answer; approving blind is refused."""
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        await _incident(db, agent)
        proposal = (await propose_cases(db, policy))[0]

        with pytest.raises(ValueError, match="expected_output or required_substrings"):
            await EvaluationService(db).approve_case(agent.org_id, proposal.id, {})


async def test_approval_bumps_dataset_version_and_makes_case_gradeable(
    session_factory,
) -> None:
    async with session_factory() as db:
        agent, suite, policy = await _seed(db)
        await _incident(db, agent)
        proposal = (await propose_cases(db, policy))[0]
        version_before = suite.dataset_version

        approved = await EvaluationService(db).approve_case(
            agent.org_id, proposal.id, {"expected_output": "a safe refusal"}
        )
        await db.refresh(suite)
        graded = await EvaluationService(db).list_cases(agent.org_id, suite.id)

    assert approved.approved is True
    assert suite.dataset_version == version_before + 1
    assert approved.added_in_version == suite.dataset_version
    assert [c.id for c in graded] == [approved.id]


async def test_rejecting_a_proposal_leaves_the_dataset_untouched(session_factory) -> None:
    async with session_factory() as db:
        agent, suite, policy = await _seed(db)
        await _incident(db, agent)
        proposal = (await propose_cases(db, policy))[0]
        version_before = suite.dataset_version

        removed = await EvaluationService(db).reject_case(agent.org_id, proposal.id)
        await db.refresh(suite)
        result = await db.execute(
            select(EvaluationCase).where(EvaluationCase.suite_id == suite.id)
        )
        remaining = list(result.scalars().all())

    assert removed is True
    assert remaining == []
    assert suite.dataset_version == version_before


async def test_sampler_is_tenant_scoped(session_factory) -> None:
    async with session_factory() as db:
        agent, _suite, policy = await _seed(db)
        other = Organization(name="Other", slug="other-sampler")
        db.add(other)
        await db.commit()
        await db.refresh(other)

        # An incident belonging to a different tenant must be invisible.
        stray = Session(org_id=other.id, agent_id=agent.id, title="stray")
        db.add(stray)
        await db.commit()
        await db.refresh(stray)
        db.add(
            AuditLog(
                org_id=other.id,
                action="guardrail.injection_flagged",
                resource_type="tool",
                metadata_={"run_id": stray.id},
            )
        )
        await db.commit()

        candidates = await find_candidates(db, policy)

    assert candidates == []
