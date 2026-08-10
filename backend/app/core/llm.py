from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.provider import Provider

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.config import get_settings

settings = get_settings()

# Errors worth one retry because they are about the connection/provider load,
# not the request itself — retrying a bad request would just fail the same
# way again slower. Only applied before any chunk has been yielded (see
# `LLMClient.stream`): once content has streamed to the caller, retrying would
# re-run the whole prompt and duplicate/conflict with what was already sent.
_TRANSIENT_LLM_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
_STREAM_CONNECT_RETRIES = 2
_STREAM_CONNECT_BACKOFF_SECONDS = 0.5


def _thinking_tool_choice_error(exc: BadRequestError, tool_choice: Any | None) -> bool:
    message = str(exc).lower()
    return isinstance(tool_choice, dict) and "tool_choice" in message and "thinking mode" in message


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
        tool_choice: Any | None = None,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
        """Non-streaming completion. Returns (content, usage, tool_calls)."""
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice if tool_choice is not None else "auto"
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # Qwen-compatible providers reject function tool_choice while
            # thinking is enabled. Tool calls are still supported when
            # thinking is disabled for this request.
            if not _thinking_tool_choice_error(exc, tool_choice):
                raise
            kwargs["extra_body"] = {"enable_thinking": False}
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
        tool_choice: Any | None = None,
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
            kwargs["tool_choice"] = tool_choice if tool_choice is not None else "auto"

        async def _open() -> Any:
            try:
                return await self._client.chat.completions.create(stream=True, **kwargs)
            except TypeError:
                # Servers that are not fully OpenAI-compatible reject stream_options.
                kwargs.pop("stream_options", None)
                return await self._client.chat.completions.create(stream=True, **kwargs)
            except BadRequestError as exc:
                if not _thinking_tool_choice_error(exc, tool_choice):
                    raise
                kwargs["extra_body"] = {"enable_thinking": False}
                return await self._client.chat.completions.create(stream=True, **kwargs)

        stream = None
        for attempt in range(_STREAM_CONNECT_RETRIES + 1):
            try:
                stream = await _open()
                break
            except _TRANSIENT_LLM_ERRORS:
                if attempt == _STREAM_CONNECT_RETRIES:
                    raise
                await asyncio.sleep(_STREAM_CONNECT_BACKOFF_SECONDS * (attempt + 1))

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
            # Reasoning-class models (DeepSeek-R1, o1/o3) stream their
            # chain-of-thought in a non-content field; surface it so the UI
            # can render live "thinking" instead of an opaque spinner.
            reasoning = (
                getattr(delta, "reasoning_content", None)
                or getattr(delta, "reasoning", None)
                or ""
            )
            if reasoning:
                yield {"type": "reasoning", "text": reasoning}
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
