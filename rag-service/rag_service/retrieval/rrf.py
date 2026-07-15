"""Reciprocal Rank Fusion (RRF).

Combines several ranked lists into one without normalizing scores across
different retrieval systems. See Cormack et al. (2009).
"""

from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse ranked lists of ``(id, score)`` into ``[(id, rrf_score)]``.

    Only rank positions matter; the per-list ``score`` values are ignored.
    ``weights`` optionally scales each list's contribution.
    """
    if not ranked_lists:
        return []
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights must match number of ranked lists")

    scores: dict[str, float] = {}
    for ranked_list, weight in zip(ranked_lists, weights):
        for rank, (chunk_id, _score) in enumerate(ranked_list, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
