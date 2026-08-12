from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.providers.constants import DEFAULT_CONTEXT_WINDOW
from app.core.providers.driver import LLMDriver, ModelInfo, TestResult
from app.core.providers.templates import ProviderTemplate
from app.db.base import utc_now

TEST_TIMEOUT_SECONDS = 15.0
DISCOVERY_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class DiscoveryResult:
    test: TestResult
    models: list[ModelInfo]
    discovery_success: bool
    discovery_error: str | None = None
    used_fallback: bool = False
    attempted_at: datetime | None = None


class ModelDiscoveryService:
    @staticmethod
    async def probe(driver: LLMDriver, template: ProviderTemplate) -> DiscoveryResult:
        attempted_at = utc_now()
        try:
            test = await asyncio.wait_for(
                driver.test_connection(), timeout=TEST_TIMEOUT_SECONDS
            )
        except TimeoutError:
            test = TestResult(False, int(TEST_TIMEOUT_SECONDS * 1000), "connection timeout")
        except Exception as exc:  # noqa: BLE001
            test = TestResult(False, 0, f"connection error: {type(exc).__name__}")
        if not test.ok:
            return DiscoveryResult(test, [], False, test.message, attempted_at=attempted_at)

        try:
            models = await asyncio.wait_for(
                driver.list_models(), timeout=DISCOVERY_TIMEOUT_SECONDS
            )
            return DiscoveryResult(
                test,
                models,
                True,
                attempted_at=attempted_at,
            )
        except TimeoutError:
            error = "model discovery timeout"
        except Exception as exc:  # noqa: BLE001
            error = f"model discovery error: {type(exc).__name__}"

        fallback = [
            ModelInfo(
                name=item.name,
                display_name=item.display_name,
                context_window=item.context_window,
                input_cost_per_1k=item.input_cost_per_1k,
                output_cost_per_1k=item.output_cost_per_1k,
                supports_tools=item.supports_tools,
                supports_reasoning=item.supports_reasoning,
                supports_vision=item.supports_vision,
            )
            for item in template.fallback_models
        ]
        return DiscoveryResult(
            test,
            fallback,
            False,
            error,
            used_fallback=bool(fallback),
            attempted_at=attempted_at,
        )

    @staticmethod
    def model_values(
        info: ModelInfo,
        *,
        source: str,
        template: ProviderTemplate,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "name": info.name,
            "display_name": info.display_name or info.name,
            "context_window": info.context_window or DEFAULT_CONTEXT_WINDOW,
            "input_cost_per_1k": info.input_cost_per_1k or 0.0,
            "output_cost_per_1k": info.output_cost_per_1k or 0.0,
            "source": source,
            "discovered": source == "discovered",
            "last_seen_at": now if source == "discovered" else None,
            "last_discovered_at": now,
            "catalog_source": template.catalog_source if source == "fallback" else None,
            "catalog_version": template.catalog_version if source == "fallback" else None,
            "supports_tools": info.supports_tools,
            "supports_reasoning": info.supports_reasoning,
            "supports_vision": info.supports_vision,
        }
