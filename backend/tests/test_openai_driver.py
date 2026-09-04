from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.providers.driver import model_info_from_mapping
from app.core.providers.openai_driver import OpenAICompatibleDriver
from app.core.tools.registry import BUILTIN_TOOLS
from app.core.tools.types import tool_to_openai_schema


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
