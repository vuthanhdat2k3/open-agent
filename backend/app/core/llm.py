from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.provider import Provider

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()


def resolve_api_key(provider: Provider) -> str:
    """Return the API key for a provider.

    Uses the directly-stored ``api_key`` first; falls back to the environment
    variable named by ``env_var`` so users can still keep secrets in ``.env``.
    """
    key = getattr(provider, "api_key", "") or ""
    if not key:
        key = os.environ.get(getattr(provider, "env_var", "") or "", "")
    if not key:
        raise RuntimeError(
            f"Provider '{getattr(provider, 'name', '?')}' has no API key configured "
            f"(set api_key, or the {getattr(provider, 'env_var', '')!r} env var)."
        )
    return key


class LLMClient:
    """Thin async wrapper around an OpenAI-compatible chat completion endpoint."""

    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model_name = model_name
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
        """Non-streaming completion. Returns (content, usage, tool_calls)."""
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        content = msg.content or ""
        usage = {
            "input_tokens": (resp.usage.prompt_tokens if resp.usage else 0),
            "output_tokens": (resp.usage.completion_tokens if resp.usage else 0),
        }
        tool_calls: list[dict[str, Any]] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            )
        return content, usage, tool_calls

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming completion. Yields dicts:
        {"type": "content", "text": str},
        {"type": "tool_calls", "tool_calls": [delta, ...]}, or
        {"type": "usage", "usage": {...}, "estimated": bool,
         "finish_reasons": [...]} as the final event.

        ``stream_options.include_usage`` asks the provider for real token
        counts on the terminal chunk. Providers that ignore the option (or
        reject it) still get a usage event, flagged ``estimated=True`` so
        callers never present a guess as a measurement.
        """
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            stream = await self._client.chat.completions.create(stream=True, **kwargs)
        except TypeError:
            # Servers that are not fully OpenAI-compatible reject stream_options.
            kwargs.pop("stream_options", None)
            stream = await self._client.chat.completions.create(stream=True, **kwargs)

        usage: dict[str, int] | None = None
        finish_reasons: list[str] = []
        async for chunk in stream:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage:
                usage = {
                    "input_tokens": chunk_usage.prompt_tokens or 0,
                    "output_tokens": chunk_usage.completion_tokens or 0,
                }
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if getattr(choice, "finish_reason", None):
                finish_reasons.append(choice.finish_reason)
            delta = choice.delta
            if delta and delta.content:
                yield {"type": "content", "text": delta.content}
            tcs = getattr(delta, "tool_calls", None)
            if tcs:
                yield {"type": "tool_calls", "tool_calls": tcs}

        yield {
            "type": "usage",
            "usage": usage or {"input_tokens": 0, "output_tokens": 0},
            "estimated": usage is None,
            "finish_reasons": finish_reasons,
        }

    @staticmethod
    def estimate_cost(model_row: Any, usage: dict[str, int]) -> float:
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        return (inp / 1000.0) * float(getattr(model_row, "input_cost_per_1k", 0) or 0) + (
            out / 1000.0
        ) * float(getattr(model_row, "output_cost_per_1k", 0) or 0)
