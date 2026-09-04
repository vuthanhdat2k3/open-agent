from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.providers.driver import model_info_from_mapping
from app.core.providers.openai_driver import OpenAICompatibleDriver
from app.core.tools.registry import BUILTIN_TOOLS
from app.core.tools.types import tool_to_openai_schema


async def test_stream_bounds_total_duration_even_with_fast_chunks() -> None:
    """Regression guard: a provider dribbling out chunks well under the
    per-chunk gap timeout, indefinitely, must still be cut off by the
    overall wall-clock cap - otherwise the caller's checked-out DB
    connection (see chat.py::run_chat_detached) is held forever."""

    def _chunk() -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="x", tool_calls=None),
                    finish_reason=None,
                )
            ],
            usage=None,
        )

    async def _fake_chunks():
        # Well under the 60s per-chunk gap timeout, but this generator never
        # stops on its own - only the total-duration cap should end it.
        for _ in range(1000):
            await asyncio.sleep(0.01)
            yield _chunk()

    driver = OpenAICompatibleDriver(
        "https://example.test/v1", "key", "openai-compatible-test"
    )
    with (
        patch.object(
            driver._client.chat.completions,
            "create",
            new=AsyncMock(return_value=_fake_chunks()),
        ),
        patch("app.core.llm._STREAM_TOTAL_TIMEOUT_SECONDS", 0.1),
    ):
        started = time.monotonic()
        events = [ev async for ev in driver.stream([{"role": "user", "content": "hi"}])]
        elapsed = time.monotonic() - started

    assert elapsed < 5.0, "stream() did not respect the total-duration cap"
    assert events[-1] == {
        "type": "usage",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "estimated": True,
        "finish_reasons": [],
    }
    # Cut off well before all 1000 fake chunks were consumed.
    assert sum(1 for ev in events if ev["type"] == "content") < 100


def test_model_info_from_mapping_detects_vision_by_name() -> None:
    vision_names = [
        "qwen2.5-vl-72b-instruct",
        "gpt-4-vision-preview",
        "llava-1.6-34b",
        "pixtral-12b-2409",
    ]
    for name in vision_names:
        assert model_info_from_mapping({"id": name}).supports_vision is True, name

    non_vision_names = ["qwen3.7-max", "deepseek-chat", "gpt-4o-mini"]
    for name in non_vision_names:
        assert model_info_from_mapping({"id": name}).supports_vision is None, name


async def test_openai_driver_preserves_tool_schema_and_forced_choice() -> None:
    driver = OpenAICompatibleDriver(
        "https://example.test/v1", "key", "openai-compatible-test"
    )
    tool = tool_to_openai_schema(BUILTIN_TOOLS["email_search"])
    choice = {"type": "function", "function": {"name": "email_search"}}
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[]))],
        usage=None,
    )

    with patch.object(
        driver._client.chat.completions,
        "create",
        new=AsyncMock(return_value=response),
    ) as create:
        await driver.complete(
            [{"role": "user", "content": "find mail today"}],
            tools=[tool],
            tool_choice=choice,
        )

    request = create.await_args.kwargs
    assert request["tools"] == [tool]
    assert request["tool_choice"] == choice
    assert "newer_than:1d" in request["tools"][0]["function"]["parameters"][
        "properties"
    ]["query"]["description"]
