from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelInfo:
    name: str
    display_name: str
    context_window: int | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    supports_tools: bool | None = None
    supports_reasoning: bool | None = None
    supports_vision: bool | None = None


@dataclass(frozen=True)
class TestResult:
    ok: bool
    latency_ms: int
    message: str


class LLMDriver(Protocol):
    supports_tools: bool
    supports_reasoning: bool
    supports_vision: bool

    async def test_connection(self) -> TestResult: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
        thinking: bool | None = None,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]: ...

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
        thinking: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...


_VISION_NAME_MARKERS = ("vision", "-vl", "vl-", "_vl", "vl_", "vl2", "multimodal", "llava", "pixtral")


def model_info_from_mapping(item: Mapping[str, Any]) -> ModelInfo:
    name = str(item.get("id") or item.get("name") or "").strip()
    lowered = name.lower()
    return ModelInfo(
        name=name,
        display_name=name.rsplit("/", 1)[-1].replace("-", " ").title(),
        supports_reasoning=(True if any(x in lowered for x in ("reason", "r1", "o1", "o3")) else None),
        # Best-effort like the reasoning heuristic above: only catches models
        # that self-identify vision support in their name (e.g. "qwen2.5-vl",
        # "llava-1.6"). A vision-capable model with no such marker (e.g.
        # Qwen3.5's natively-multimodal line) still needs Model.supports_vision
        # set explicitly - this is a floor, not a source of truth.
        supports_vision=(True if any(x in lowered for x in _VISION_NAME_MARKERS) else None),
    )
