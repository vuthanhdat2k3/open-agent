"""Retrieval quality checks.

Tool-call failures are where agent incidents surface, but bad retrieval is
usually the upstream cause. M11 could only grade the final answer, so a
suite could stay green while retrieval quietly rotted. These graders score
the retrieval step itself.

All three are deterministic and need no model call, so they run in CI
without provider credentials.
"""

from __future__ import annotations

import re
from typing import Any

# Words too common to count as evidence that a sentence came from a source.
_STOPWORDS = frozenset(
    [
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "have", "in", "is", "it", "its", "of", "on", "or", "that",
        "the", "this", "to", "was", "were", "will", "with",
    ]
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[\w']+", re.UNICODE)


def recall_at_k(expected: list[str], retrieved: list[str], k: int | None = None) -> float:
    """Fraction of expected documents present in the top ``k`` retrieved.

    Returns 1.0 when nothing was expected: a case with no retrieval
    expectation must not be penalised.
    """
    if not expected:
        return 1.0
    window = retrieved[:k] if k else retrieved
    hits = len(set(expected) & set(window))
    return hits / len(set(expected))


def mean_reciprocal_rank(expected: list[str], retrieved: list[str]) -> float:
    """Reciprocal rank of the first expected document (0.0 if none appear).

    Rewards ranking the right chunk first rather than merely including it,
    which is what actually matters once the context window is tight.
    """
    if not expected:
        return 1.0
    wanted = set(expected)
    for index, doc_id in enumerate(retrieved, start=1):
        if doc_id in wanted:
            return 1.0 / index
    return 0.0


def _content_words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(text)} - _STOPWORDS


def groundedness(output: str, sources: list[str], *, threshold: float = 0.5) -> float:
    """Fraction of output sentences supported by the retrieved sources.

    A sentence counts as supported when enough of its content words appear
    in some source. This is a lexical heuristic: it reliably catches an
    answer invented from nothing, but not a subtly wrong paraphrase of a
    real source.

    ponytail: word-overlap heuristic; swap in an NLI model if the
    false-negative rate on paraphrased answers becomes a problem.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(output or "") if s.strip()]
    if not sentences:
        return 1.0
    if not sources:
        return 0.0

    source_words: set[str] = set()
    for source in sources:
        source_words |= _content_words(source)

    supported = 0
    for sentence in sentences:
        words = _content_words(sentence)
        if not words:
            # No content words to check (e.g. "Yes.") — not evidence of
            # fabrication, so it does not count against the score.
            supported += 1
            continue
        if len(words & source_words) / len(words) >= threshold:
            supported += 1
    return supported / len(sentences)


def grade_retrieval(
    case: Any,
    *,
    output: str,
    retrieved_doc_ids: list[str],
    retrieved_texts: list[str] | None = None,
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Return ``(checks, details)`` for whichever thresholds the case sets.

    A case that declares no retrieval expectations produces no checks, so
    existing M11 suites grade exactly as before.
    """
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    expected = list(getattr(case, "expected_doc_ids", None) or [])
    k = getattr(case, "retrieval_k", None)
    min_recall = getattr(case, "min_recall_at_k", None)
    min_ground = getattr(case, "min_groundedness", None)

    if expected:
        recall = recall_at_k(expected, retrieved_doc_ids, k)
        mrr = mean_reciprocal_rank(expected, retrieved_doc_ids)
        details["recall_at_k"] = recall
        details["mrr"] = mrr
        details["retrieved_doc_ids"] = retrieved_doc_ids
        if min_recall is not None:
            checks[f"min_recall_at_{k or 'all'}"] = recall >= min_recall

    if min_ground is not None:
        score = groundedness(output, retrieved_texts or [])
        details["groundedness"] = score
        checks["min_groundedness"] = score >= min_ground

    return checks, details
