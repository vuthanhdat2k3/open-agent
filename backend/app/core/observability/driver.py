"""Provider-neutral instrumentation wrapper for LLM drivers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.core.observability.llm_trace import ObservabilityContext
from app.core.providers.driver import LLMDriver, ModelInfo, TestResult


class ObservableLLMDriver:
    """Decorate any LLMDriver without changing its public runtime contract."""

    def __init__(
        self,
        inner: LLMDriver,
        observability: ObservabilityContext,
        *,
        provider: str,
        model: str,
        generation_name: str = "model-generation",
        cost_rates: tuple[float, float] | None = None,
    ) -> None:
        self._inner = inner
        self._observability = observability
        self._provider = provider
        self._model = model
        self._generation_name = generation_name
        # (input_cost_per_1k, output_cost_per_1k) from the Model row, if the
        # caller has one. Lets us report real cost on every Langfuse
        # generation instead of leaving it blank/priced by Langfuse's own
        # (often stale or missing) model price table.
        self._cost_rates = cost_rates
        self.last_observation_id: str | None = None
        self.supports_tools = inner.supports_tools
        self.supports_reasoning = inner.supports_reasoning
        self.supports_vision = inner.supports_vision

    def _cost_usd(self, usage: dict[str, Any]) -> float | None:
        if not self._cost_rates or not usage:
            return None
        rate_in, rate_out = self._cost_rates
        return (usage.get("input_tokens", 0) / 1000.0) * rate_in + (
            usage.get("output_tokens", 0) / 1000.0
        ) * rate_out

    async def test_connection(self) -> TestResult:
        return await self._inner.test_connection()

    async def list_models(self) -> list[ModelInfo]:
        return await self._inner.list_models()

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
        thinking: bool | None = None,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
        handle = self._observability.start_generation(
            name=self._generation_name,
            provider=self._provider,
            model=self._model,
            input=messages,
            metadata={
                "temperature": temperature,
                "tool_count": len(tools or []),
                "tool_choice": tool_choice,
            },
        )
        self.last_observation_id = handle.observation_id
        try:
            result = await self._inner.complete(
                messages,
                tools=tools,
                temperature=temperature,
                tool_choice=tool_choice,
                thinking=thinking,
            )
            content, usage, tool_calls = result
            handle.finish_success(
                output=content,
                usage=usage,
                tool_calls=tool_calls,
                cost_usd=self._cost_usd(usage),
            )
            return result
        except asyncio.CancelledError:
            handle.finish_cancelled()
            raise
        except Exception as exc:
            handle.finish_error(exc)
            raise

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
        thinking: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async def _stream() -> AsyncIterator[dict[str, Any]]:
            handle = self._observability.start_generation(
                name=self._generation_name,
                provider=self._provider,
                model=self._model,
                input=messages,
                metadata={
                    "temperature": temperature,
                    "tool_count": len(tools or []),
                    "tool_choice": tool_choice,
                },
            )
            self.last_observation_id = handle.observation_id
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            usage: dict[str, int] = {}
            usage_estimated: bool | None = None
            try:
                async for event in self._inner.stream(
                    messages,
                    tools=tools,
                    temperature=temperature,
                    tool_choice=tool_choice,
                    thinking=thinking,
                ):
                    event_type = event.get("type")
                    if event_type == "content":
                        content_parts.append(str(event.get("text") or ""))
                    elif event_type == "reasoning":
                        reasoning_parts.append(str(event.get("text") or ""))
                    elif event_type == "tool_calls":
                        tool_calls.extend(event.get("tool_calls") or [])
                    elif event_type == "usage":
                        usage = dict(event.get("usage") or {})
                        usage_estimated = event.get("estimated")
                    yield event
                output = {
                    "content": "".join(content_parts),
                    "reasoning": "".join(reasoning_parts),
                }
                handle.finish_success(
                    output=output,
                    usage=usage,
                    tool_calls=tool_calls,
                    cost_usd=self._cost_usd(usage),
                    estimated=usage_estimated,
                )
            except asyncio.CancelledError:
                handle.finish_cancelled(
                    output={
                        "content": "".join(content_parts),
                        "reasoning": "".join(reasoning_parts),
                    }
                )
                raise
            except Exception as exc:
                handle.finish_error(
                    exc,
                    output={
                        "content": "".join(content_parts),
                        "reasoning": "".join(reasoning_parts),
                    },
                    usage=usage,
                    tool_calls=tool_calls,
                )
                raise
            finally:
                handle.finish_cancelled(
                    output={
                        "content": "".join(content_parts),
                        "reasoning": "".join(reasoning_parts),
                    },
                    usage=usage,
                    tool_calls=tool_calls,
                )

        return _stream()
