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
    ) -> None:
        self._inner = inner
        self._observability = observability
        self._provider = provider
        self._model = model
        self._generation_name = generation_name
        self.last_observation_id: str | None = None
        self.supports_tools = inner.supports_tools
        self.supports_reasoning = inner.supports_reasoning
        self.supports_vision = inner.supports_vision

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
            handle.finish_success(output=content, usage=usage, tool_calls=tool_calls)
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
                    yield event
                output = {
                    "content": "".join(content_parts),
                    "reasoning": "".join(reasoning_parts),
                }
                handle.finish_success(output=output, usage=usage, tool_calls=tool_calls)
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
