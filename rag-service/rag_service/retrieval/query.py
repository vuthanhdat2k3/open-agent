"""Query Optimizer & Transformation module.

Implements HyDE (Hypothetical Document Embeddings) and Sub-Query Decomposition.
"""

from __future__ import annotations

import re


class QueryOptimizer:
    """Optimizes and transforms raw user queries into improved retrieval queries."""

    @staticmethod
    def generate_hyde_prompt(query: str) -> str:
        """Build a HyDE prompt asking the LLM to generate a hypothetical answer passage."""
        return (
            f"Please write a scientific/technical passage that answers the following query:\n"
            f"Query: {query}\n\n"
            f"Passage:"
        )

    @staticmethod
    def decompose_query(query: str) -> list[str]:
        """Decompose a complex multi-part query into atomic sub-queries."""
        cleaned = query.strip()
        if not cleaned:
            return []

        # Split on conjunctions or clauses if complex
        split_pattern = re.compile(r"\s+(?:and|or|vs|versus|compared to|\,|\;)\s+", re.IGNORECASE)
        parts = [p.strip() for p in split_pattern.split(cleaned) if p.strip()]

        if len(parts) > 1:
            return [cleaned] + parts
        return [cleaned]
