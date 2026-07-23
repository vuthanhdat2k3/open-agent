from __future__ import annotations

from enum import Enum


class RiskTier(str, Enum):
    """Risk classification for every tool.

    Used by the 2-layer capability gate (agent-level → org/role-level via ``agent.allowed_risk_tiers``).
    """

    safe = "safe"  # memory tools, no side effects
    read = "read"  # read-only file/network access
    write = "write"  # write files inside workspace
    execute = "execute"  # run code in sandbox
    network = "network"  # outbound network (web_search)
    dangerous = "dangerous"  # arbitrary shell, no sandbox
