"""M15 — retrieval graders.

Retrieval is the upstream cause of most multi-layer agent incidents, but
M11 could only grade the final answer. These graders must stay
deterministic and credential-free so the quality gate can run in CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evals.graders.retrieval import (
    grade_retrieval,
    groundedness,
    mean_reciprocal_rank,
    recall_at_k,
)


@dataclass
class _Case:
    """Stand-in for the EvaluationCase fields the graders read."""

    expected_doc_ids: list[str] = field(default_factory=list)
    retrieval_k: int | None = None
    min_recall_at_k: float | None = None
    min_groundedness: float | None = None


# --------------------------------------------------------------------------- #
# recall@k
# --------------------------------------------------------------------------- #
def test_recall_counts_only_the_top_k_window() -> None:
    expected = ["a", "b", "c"]
    retrieved = ["a", "x", "b", "y", "z", "c"]

    assert recall_at_k(expected, retrieved, 5) == 2 / 3
    assert recall_at_k(expected, retrieved) == 1.0


def test_recall_is_one_when_nothing_was_expected() -> None:
    """A case with no retrieval expectation must not be penalised."""
    assert recall_at_k([], ["anything"]) == 1.0


def test_recall_is_zero_when_nothing_relevant_retrieved() -> None:
    assert recall_at_k(["a"], ["x", "y"]) == 0.0


# --------------------------------------------------------------------------- #
# MRR
# --------------------------------------------------------------------------- #
def test_mrr_rewards_ranking_the_right_chunk_first() -> None:
    assert mean_reciprocal_rank(["target"], ["target", "x", "y"]) == 1.0
    assert mean_reciprocal_rank(["target"], ["x", "y", "target"]) == 1 / 3


def test_mrr_is_zero_when_expected_never_appears() -> None:
    assert mean_reciprocal_rank(["target"], ["x", "y"]) == 0.0


# --------------------------------------------------------------------------- #
# Groundedness
# --------------------------------------------------------------------------- #
def test_grounded_answer_scores_high() -> None:
    source = "The retry budget defaults to three attempts before the run fails."
    output = "The retry budget defaults to three attempts."

    assert groundedness(output, [source]) >= 0.9


def test_fabricated_answer_scores_low() -> None:
    """The heuristic must catch an answer invented from nothing."""
    source = "The retry budget defaults to three attempts."
    output = "Quarterly revenue grew fourteen percent across European markets."

    assert groundedness(output, [source]) < 0.5


def test_no_sources_means_nothing_is_grounded() -> None:
    assert groundedness("Some claim about the system.", []) == 0.0


def test_empty_output_is_not_counted_as_fabrication() -> None:
    assert groundedness("", ["anything"]) == 1.0


# --------------------------------------------------------------------------- #
# grade_retrieval integration
# --------------------------------------------------------------------------- #
def test_case_without_expectations_produces_no_checks() -> None:
    """Existing M11 suites must grade exactly as before."""
    checks, details = grade_retrieval(_Case(), output="anything", retrieved_doc_ids=["a"])

    assert checks == {}
    assert details == {}


def test_recall_threshold_failure_is_reported() -> None:
    case = _Case(expected_doc_ids=["a", "b"], retrieval_k=2, min_recall_at_k=1.0)

    checks, details = grade_retrieval(
        case, output="irrelevant", retrieved_doc_ids=["a", "zzz", "b"]
    )

    # "b" sits outside the top-2 window, so recall is 0.5 and the gate fails.
    assert checks["min_recall_at_2"] is False
    assert details["recall_at_k"] == 0.5


def test_recall_threshold_pass_is_reported() -> None:
    case = _Case(expected_doc_ids=["a"], retrieval_k=2, min_recall_at_k=1.0)

    checks, details = grade_retrieval(case, output="irrelevant", retrieved_doc_ids=["a", "b"])

    assert checks["min_recall_at_2"] is True
    assert details["mrr"] == 1.0


def test_metrics_recorded_even_without_a_threshold() -> None:
    """Numbers are worth seeing before deciding what the threshold should be."""
    case = _Case(expected_doc_ids=["a"])

    checks, details = grade_retrieval(case, output="x", retrieved_doc_ids=["z", "a"])

    assert checks == {}
    assert details["recall_at_k"] == 1.0
    assert details["mrr"] == 0.5


def test_groundedness_threshold_is_enforced() -> None:
    case = _Case(min_groundedness=0.8)
    source = "Workflow runs resume from the last successful node."

    passing, _ = grade_retrieval(
        case,
        output="Workflow runs resume from the last successful node.",
        retrieved_doc_ids=[],
        retrieved_texts=[source],
    )
    failing, _ = grade_retrieval(
        case,
        output="Pricing tiers changed last quarter for enterprise customers.",
        retrieved_doc_ids=[],
        retrieved_texts=[source],
    )

    assert passing["min_groundedness"] is True
    assert failing["min_groundedness"] is False


def test_graders_need_no_provider_credentials() -> None:
    """Guards the M11 rule: the gate must run in CI without a model."""
    import inspect

    from app.evals.graders import retrieval

    source = inspect.getsource(retrieval)
    for forbidden in ("openai", "LLMClient", "api_key", "httpx"):
        assert forbidden not in source, f"retrieval graders must stay offline ({forbidden})"
