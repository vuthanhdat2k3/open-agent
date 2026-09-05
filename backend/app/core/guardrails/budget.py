from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunBudget:
    max_tool_calls: int = 40
    max_cost_usd: float = 2.0
    max_wall_seconds: float = 300.0
    max_repeated_call: int = 3


@dataclass
class BudgetTracker:
    budget: RunBudget
    started_at: float = field(default_factory=time.monotonic)
    tool_calls: int = 0
    cost_usd: float = 0.0
    repeated_calls: dict[str, int] = field(default_factory=dict)
    last_reason: str | None = None

    def _call_key(self, name: str, args: dict[str, Any]) -> str:
        payload = json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
        digest = hashlib.sha256(f"{name}:{payload}".encode()).hexdigest()
        return f"{name}:{digest}"

    def record_call(self, name: str, args: dict[str, Any], cost_usd: float = 0.0) -> str | None:
        self.tool_calls += 1
        self.cost_usd += cost_usd
        key = self._call_key(name, args)
        self.repeated_calls[key] = self.repeated_calls.get(key, 0) + 1
        return self.exceeded()

    def add_cost(self, cost_usd: float) -> str | None:
        """Accumulate model-request cost and re-check the budget.

        Returns the exceeded reason when the budget trips, else None.
        """
        if cost_usd > 0:
            self.cost_usd += cost_usd
        return self.exceeded()

    def exceeded(self) -> str | None:
        if self.tool_calls > self.budget.max_tool_calls:
            self.last_reason = f"max_tool_calls exceeded ({self.tool_calls}>{self.budget.max_tool_calls})"
            return self.last_reason
        if self.cost_usd > self.budget.max_cost_usd:
            self.last_reason = f"max_cost_usd exceeded ({self.cost_usd:.4f}>{self.budget.max_cost_usd:.4f})"
            return self.last_reason
        elapsed = time.monotonic() - self.started_at
        if elapsed > self.budget.max_wall_seconds:
            self.last_reason = f"max_wall_seconds exceeded ({elapsed:.1f}>{self.budget.max_wall_seconds:.1f})"
            return self.last_reason
        max_repeated = max(self.repeated_calls.values(), default=0)
        if max_repeated > self.budget.max_repeated_call:
            self.last_reason = (
                f"max_repeated_call exceeded ({max_repeated}>{self.budget.max_repeated_call})"
            )
            return self.last_reason
        self.last_reason = None
        return None

