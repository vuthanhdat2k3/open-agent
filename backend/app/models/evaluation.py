from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class EvaluationSuite(Base):
    __tablename__ = "evaluation_suites"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_evaluation_suites_org_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    dataset_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint("suite_id", "ordinal", name="uq_evaluation_cases_suite_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_substrings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    forbidden_patterns: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    max_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    added_in_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # --- Provenance (M15) ---
    # "manual" | "sampled". A sampled case starts unapproved because only a
    # human knows what the right answer should have been; the sampler
    # proposes, it does not decide.
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_run_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sampled_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Retrieval expectations (M15) ---
    # Retrieval is the upstream cause of most multi-layer agent incidents,
    # but nothing in M11 could measure it.
    expected_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    min_recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_release_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_releases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    baseline_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_runs.id", ondelete="SET NULL"), nullable=True
    )
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False, index=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    triggered_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", name="uq_evaluation_results_run_case"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    observed_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Chunks the run actually retrieved, so recall@k / MRR can be scored
    # against expected_doc_ids without re-running retrieval.
    retrieved_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grader_details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
