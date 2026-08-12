from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx

from app.core.providers.driver import ModelInfo, TestResult

_GEMINI_SCHEMA_KEYS = frozenset(
    {
        "type",
        "format",
        "title",
        "description",
        "nullable",
        "enum",
        "maxItems",
        "minItems",
        "properties",
        "required",
        "minProperties",
        "maxProperties",
        "items",
        "anyOf",
        "propertyOrdering",
    }
)


def _normalize_schema_for_gemini(schema: Any) -> dict[str, Any]:
    """Convert a JSON Schema object to Gemini's supported Schema dialect.

    Tool specs are authored in the OpenAI JSON-Schema dialect. Gemini's
    ``Schema`` message is only a subset and rejects fields such as
    ``additionalProperties`` with HTTP 400. Normalize at this adapter boundary
    so OpenAI-compatible and Anthropic drivers continue receiving the original
    schema unchanged.
    """
    if not isinstance(schema, dict):
        return {"type": "OBJECT"}

    normalized: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _GEMINI_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            normalized[key] = {
                name: _normalize_schema_for_gemini(property_schema)
                for name, property_schema in value.items()
            }
        elif key == "items":
            normalized[key] = _normalize_schema_for_gemini(value)
        elif key == "anyOf" and isinstance(value, list):
            variants = [_normalize_schema_for_gemini(item) for item in value]
            non_null = [
                item for item in variants if str(item.get("type", "")).upper() != "NULL"
            ]
            if len(non_null) == 1 and len(non_null) != len(variants):
                normalized.update(non_null[0])
                normalized["nullable"] = True
            else:
                normalized[key] = variants
        else:
            normalized[key] = value

    schema_type = normalized.get("type")
    if isinstance(schema_type, list):
        non_null_types = [item for item in schema_type if str(item).lower() != "null"]
        if len(non_null_types) == 1:
            normalized["type"] = non_null_types[0]
            if len(non_null_types) != len(schema_type):
                normalized["nullable"] = True
        elif non_null_types:
            normalized["anyOf"] = [{"type": item} for item in non_null_types]
            normalized.pop("type", None)
            if len(non_null_types) != len(schema_type):
                normalized["nullable"] = True
        else:
            normalized.pop("type", None)
            normalized["nullable"] = True

    return normalized


class GeminiDriver:
    supports_tools = True
    supports_reasoning = True
    supports_vision = True

    def __init__(self, base_url: str, api_key: str, model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name.removeprefix("models/")

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "content-type": "application/json"}

    def _url(self, path: str, *, stream: bool = False) -> str:
        if path == "/models":
            return f"{self.base_url}/models"
        suffix = ":streamGenerateContent?alt=sse" if stream else ":generateContent"
        return f"{self.base_url}/models/{self.model_name}{suffix}"

    async def test_connection(self) -> TestResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(self._url("/models"), headers=self._headers())
            elapsed = int((time.monotonic() - start) * 1000)
            if response.status_code != 200:
                return TestResult(False, elapsed, f"HTTP {response.status_code}")
            return TestResult(True, elapsed, "connected")
        except Exception as exc:  # noqa: BLE001
            return TestResult(False, int((time.monotonic() - start) * 1000), f"connection error: {type(exc).__name__}")

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(self._url("/models"), headers=self._headers())
        response.raise_for_status()
        result: list[ModelInfo] = []
        for item in response.json().get("models", []):
            name = str(item.get("name", "")).removeprefix("models/")
            if not name or "generateContent" not in item.get("supportedGenerationMethods", ["generateContent"]):
                continue
            result.append(
                ModelInfo(
                    name=name,
                    display_name=item.get("displayName") or name,
                    context_window=item.get("inputTokenLimit"),
                    supports_tools=True if "function" in str(item).lower() else None,
                    supports_vision=True if "vision" in str(item).lower() else None,
                )
            )
        return result

    @staticmethod
    def _parts(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, list):
            return content
        return [{"text": str(content or "")}]

    def _payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
    ) -> dict[str, Any]:
        system_parts: list[dict[str, Any]] = []
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                system_parts.extend(self._parts(message.get("content")))
                continue
            if role == "tool":
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": message.get("name", message.get("tool_call_id", "tool")),
                            "response": {"content": str(message.get("content", ""))},
                        }
                    }],
                })
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": self._parts(message.get("content"))})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if tools:
            payload["tools"] = [{
                "functionDeclarations": [
                    {
                        "name": tool["function"]["name"],
                        "description": tool["function"].get("description", ""),
                        "parameters": _normalize_schema_for_gemini(
                            tool["function"].get("parameters", {"type": "object"})
                        ),
                    }
                    for tool in tools
                ]
            }]
        return payload

    @staticmethod
    def _response(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
        text: list[str] = []
        calls: list[dict[str, Any]] = []
        for candidate in payload.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text"):
                    if part.get("thought"):
                        text.append(f"__REASONING__{part['text']}")
                    else:
                        text.append(part["text"])
                if part.get("functionCall"):
                    call = part["functionCall"]
                    call_index = len(calls)
                    calls.append({
                        "index": call_index,
                        "id": f"{call.get('name', 'call')}-{call_index}-{uuid4().hex[:8]}",
                        "name": call.get("name", ""),
                        "arguments": json.dumps(call.get("args", {})),
                    })
        metadata = payload.get("usageMetadata", {})
        return "".join(text), calls, {
            "input_tokens": int(metadata.get("promptTokenCount", 0)),
            "output_tokens": int(metadata.get("candidatesTokenCount", 0)),
        }

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
    ) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self._url("/generate"), headers=self._headers(), json=self._payload(messages, tools, temperature))
        response.raise_for_status()
        text, calls, usage = self._response(response.json())
        return text.replace("__REASONING__", ""), usage, calls

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        tool_choice: Any | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        usage = {"input_tokens": 0, "output_tokens": 0}
        calls: list[dict[str, Any]] = []
        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream("POST", self._url("/generate", stream=True), headers=self._headers(), json=self._payload(messages, tools, temperature)) as response,
        ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    text, new_calls, chunk_usage = self._response(payload)
                    usage.update(chunk_usage)
                    calls.extend(new_calls)
                    if text:
                        marker = "__REASONING__"
                        if marker in text:
                            before, _, reasoning = text.partition(marker)
                            if before:
                                yield {"type": "content", "text": before}
                            if reasoning:
                                yield {"type": "reasoning", "text": reasoning}
                        else:
                            yield {"type": "content", "text": text}
        if calls:
            yield {"type": "tool_calls", "tool_calls": calls}
        yield {"type": "usage", "usage": usage, "estimated": False, "finish_reasons": []}
