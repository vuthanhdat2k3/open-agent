from __future__ import annotations

import time

import httpx

from app.core.llm import LLMClient
from app.core.providers.driver import ModelInfo, TestResult, model_info_from_mapping


class OpenAICompatibleDriver(LLMClient):
    """Driver for OpenAI and providers exposing the OpenAI API contract."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str = "",
        *,
        supports_tools: bool = True,
        supports_reasoning: bool = False,
        supports_vision: bool = False,
    ) -> None:
        super().__init__(base_url, api_key or "ollama", model_name)
        self._api_key = api_key
        self.supports_tools = supports_tools
        self.supports_reasoning = supports_reasoning
        self.supports_vision = supports_vision

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def test_connection(self) -> TestResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    self.base_url.rstrip("/") + "/models", headers=self._headers()
                )
            elapsed = int((time.monotonic() - start) * 1000)
            if response.status_code != 200:
                return TestResult(False, elapsed, f"HTTP {response.status_code}")
            return TestResult(True, elapsed, "connected")
        except Exception as exc:  # noqa: BLE001
            return TestResult(
                False,
                int((time.monotonic() - start) * 1000),
                f"connection error: {type(exc).__name__}",
            )

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                self.base_url.rstrip("/") + "/models", headers=self._headers()
            )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", payload if isinstance(payload, list) else [])
        return [info for item in items if (info := model_info_from_mapping(item)).name]
