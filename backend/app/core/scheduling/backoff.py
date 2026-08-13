from __future__ import annotations

import random

MAX_RETRY_COUNT = 5


def compute_backoff_seconds(retry_count: int, *, base: int = 60, cap: int = 3600) -> float:
    """Return exponential backoff with full jitter."""
    if retry_count < 0:
        raise ValueError("retry_count must be non-negative")
    ceiling = min(cap, base * (2**retry_count))
    return random.uniform(0, ceiling)
