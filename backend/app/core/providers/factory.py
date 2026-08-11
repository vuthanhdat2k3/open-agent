from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.llm import resolve_api_key
from app.core.providers.anthropic_driver import AnthropicDriver
from app.core.providers.driver import LLMDriver
from app.core.providers.gemini_driver import GeminiDriver
from app.core.providers.openai_driver import OpenAICompatibleDriver
from app.core.providers.templates import get_template

if TYPE_CHECKING:
    from app.core.observability.llm_trace import ObservabilityContext


def _capabilities(provider: Any, model: Any) -> dict[str, bool]:
    template = get_template(getattr(provider, "template_key", "") or "")
    defaults = {
        "supports_tools": template.supports_tools if template else True,
        "supports_reasoning": template.supports_reasoning if template else False,
        "supports_vision": template.supports_vision if template else False,
    }
    for key in defaults:
        value = getattr(model, key, None)
        if value is not None:
            defaults[key] = bool(value)
    return defaults


def build_driver(
    provider: Any,
    model: Any,
    *,
    observability: ObservabilityContext | None = None,
    generation_name: str = "model-generation",
) -> LLMDriver:
    template = get_template(getattr(provider, "template_key", "") or "")
    api_key = resolve_api_key(provider)
    capabilities = _capabilities(provider, model)
    if template is None:
        inner: LLMDriver = OpenAICompatibleDriver(
            provider.base_url, api_key, model.name, **capabilities
        )
    elif template.driver == "anthropic":
        driver = AnthropicDriver(provider.base_url, api_key, model.name)
        driver.supports_tools = capabilities["supports_tools"]
        driver.supports_reasoning = capabilities["supports_reasoning"]
        driver.supports_vision = capabilities["supports_vision"]
        inner = driver
    elif template.driver == "gemini":
        driver = GeminiDriver(provider.base_url, api_key, model.name)
        driver.supports_tools = capabilities["supports_tools"]
        driver.supports_reasoning = capabilities["supports_reasoning"]
        driver.supports_vision = capabilities["supports_vision"]
        inner = driver
    else:
        inner = OpenAICompatibleDriver(
            provider.base_url, api_key, model.name, **capabilities
        )

    if observability is None:
        return inner
    from app.core.observability.driver import ObservableLLMDriver

    provider_name = (
        getattr(provider, "key", None)
        or getattr(provider, "template_key", None)
        or getattr(provider, "name", None)
        or "unknown"
    )
    return ObservableLLMDriver(
        inner,
        observability,
        provider=str(provider_name),
        model=str(model.name),
        generation_name=generation_name,
    )
