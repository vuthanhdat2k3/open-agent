from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.providers.driver import ModelInfo, TestResult


class AnthropicDriver:
    supports_tools = True
    supports_reasoning = True
    supports_vision = True

    def __init__(self, base_url: str, api_key: str, model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def test_connection(self) -> TestResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{self.base_url}/v1/models", headers=self._headers())
            elapsed = int((time.monotonic() - start) * 1000)
            if response.status_code == 404:
                return TestResult(True, elapsed, "authenticated")
            if response.status_code != 200:
                return TestResult(False, elapsed, f"HTTP {response.status_code}")
            return TestResult(True, elapsed, "connected")
        except Exception as exc:  # noqa: BLE001
            return TestResult(False, int((time.monotonic() - start) * 1000), f"connection error: {type(exc).__name__}")

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/v1/models", headers=self._headers())
        if response.status_code == 404:
            raise RuntimeError("model discovery unsupported")
        response.raise_for_status()
        payload = response.json()
        return [
            ModelInfo(
                name=item["id"],
                display_name=item.get("display_name") or item["id"],
                context_window=item.get("context_window"),
            )
            for item in payload.get("data", [])
            if item.get("id")
        ]

    def _request_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        stream: bool = False,
        tool_choice: Any | None = None,
    ) -> dict[str, Any]:
        system = "\n\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                continue
            content: Any = message.get("content", "")
            if role == "tool":
                content = [{
                    "type": "tool_result",
                    "tool_use_id": message.get("tool_call_id", ""),
                    "content": str(content),
                }]
                role = "user"
            converted.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        payload: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": 8192,
            "messages": converted,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": tool["function"]["name"],
                    "description": tool["function"].get("description", ""),
                    "input_schema": tool["function"].get("parameters", {"type": "object"}),
                }
                for tool in tools
            ]
        if tool_choice and isinstance(tool_choice, dict):
            function = tool_choice.get("function", {})
            function_name = function.get("name")
            if tool_choice.get("type") == "function" and function_name:
                payload["tool_choice"] = {"type": "tool", "name": function_name}
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _response_parts(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in payload.get("content", []):
            if block.get("type") in {"text", "thinking"}:
                text_parts.append(block.get("text", block.get("thinking", "")))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                })
        usage = payload.get("usage", {})
        return "".join(text_parts), tool_calls, usage

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=self._request_payload(messages, tools, temperature, tool_choice=tool_choice),
            )
        response.raise_for_status()
        text, tool_calls, usage = self._response_parts(response.json())
        return text, {
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
        }, tool_calls

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        usage = {"input_tokens": 0, "output_tokens": 0}
        tool_buffers: dict[str, dict[str, str]] = {}
        block_index_to_id: dict[int, str] = {}
        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=self._request_payload(messages, tools, temperature, stream=True, tool_choice=tool_choice),
            ) as response,
        ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type")
                    if event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            block_id = block.get("id", "")
                            block_index_to_id[event.get("index", 0)] = block_id
                            tool_buffers[block_id] = {
                                "name": block.get("name", ""),
                                "arguments": "",
                            }
                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield {"type": "content", "text": delta.get("text", "")}
                        elif delta.get("type") == "thinking_delta":
                            yield {"type": "reasoning", "text": delta.get("thinking", "")}
                        elif delta.get("type") == "input_json_delta":
                            block_id = block_index_to_id.get(event.get("index", 0))
                            if block_id is not None and block_id in tool_buffers:
                                tool_buffers[block_id]["arguments"] += delta.get("partial_json", "")
                    elif event_type == "message_delta":
                        delta_usage = event.get("usage", {})
                        usage["output_tokens"] = int(delta_usage.get("output_tokens", 0))
                    elif event_type == "message_start":
                        usage["input_tokens"] = int(event.get("message", {}).get("usage", {}).get("input_tokens", 0))
                    elif event_type == "message_stop":
                        if tool_buffers:
                            yield {
                                "type": "tool_calls",
                                "tool_calls": [
                                    {"index": i, "id": key, "name": value["name"], "arguments": value["arguments"]}
                                    for i, (key, value) in enumerate(tool_buffers.items())
                                ],
                            }
        yield {"type": "usage", "usage": usage, "estimated": False, "finish_reasons": []}
