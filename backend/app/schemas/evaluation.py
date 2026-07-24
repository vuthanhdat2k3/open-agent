from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluationCaseCreate(BaseModel):
    input: str = Field(min_length=1, max_length=100_000)
    expected_output: str | None = Field(default=None, max_length=100_000)
    required_substrings: list[str] = Field(default_factory=list, max_length=100)
    expected_tools: list[str] = Field(default_factory=list, max_length=100)
    forbidden_patterns: list[str] = Field(default_factory=list, max_length=100)
    max_latency_ms: int | None = Field(default=None, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    metadata: dict = Field(default_factory=dict)

    @field_validator("required_substrings", "expected_tools", "forbidden_patterns")
    @classmethod
    def validate_check_lengths(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 512 for value in values):
            raise ValueError("evaluation checks must contain 1 to 512 characters")
        return values


class EvaluationCaseOut(EvaluationCaseCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    suite_id: str
    ordinal: int
    added_in_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_case(cls, case) -> EvaluationCaseOut:
        return cls(
            id=case.id,
            suite_id=case.suite_id,
            input=case.input,
            expected_output=case.expected_output,
            required_substrings=case.required_substrings,
            expected_tools=case.expected_tools,
            forbidden_patterns=case.forbidden_patterns,
            max_latency_ms=case.max_latency_ms,
            max_cost_usd=case.max_cost_usd,
            metadata=case.metadata_,
            ordinal=case.ordinal,
            added_in_version=case.added_in_version,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )


class EvaluationSuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    agent_id: str
    cases: list[EvaluationCaseCreate] = Field(default_factory=list, max_length=100)


class EvaluationSuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)


class EvaluationSuiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    agent_id: str
    dataset_version: int
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime
    cases: list[EvaluationCaseOut] = Field(default_factory=list)


class RecordedEvaluationOutput(BaseModel):
    case_id: str
    output: str
    observed_tools: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)


class EvaluationRunCreate(BaseModel):
    agent_release_id: str
    baseline_run_id: str | None = None
    execution_mode: Literal["live", "recorded"] = "live"
    recorded_outputs: list[RecordedEvaluationOutput] = Field(
        default_factory=list, max_length=100
    )


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    suite_id: str
    agent_release_id: str
    baseline_run_id: str | None
    dataset_version: int
    execution_mode: Literal["live", "recorded"]
    status: Literal["running", "completed", "failed"]
    total_cases: int
    passed_cases: int
    pass_rate: float
    average_latency_ms: float
    total_cost_usd: float
    triggered_by_user_id: str | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class EvaluationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    case_id: str
    output: str
    observed_tools: list[str]
    latency_ms: int
    cost_usd: float
    score: float
    passed: bool
    grader_details: dict
    error: str | None
    created_at: datetime


class EvaluationComparisonOut(BaseModel):
    candidate_run_id: str
    baseline_run_id: str
    pass_rate_delta: float
    average_latency_ms_delta: float
    total_cost_usd_delta: float
    regressed_case_ids: list[str]
    improved_case_ids: list[str]
