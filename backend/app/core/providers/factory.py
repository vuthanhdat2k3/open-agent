from __future__ import annotations

from typing import Any

from app.core.llm import resolve_api_key
from app.core.providers.anthropic_driver import AnthropicDriver
from app.core.providers.driver import LLMDriver
from app.core.providers.gemini_driver import GeminiDriver
from app.core.providers.openai_driver import OpenAICompatibleDriver
from app.core.providers.templates import get_template


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


def build_driver(provider: Any, model: Any) -> LLMDriver:
    template = get_template(getattr(provider, "template_key", "") or "")
    api_key = resolve_api_key(provider)
    if template is None:
        return OpenAICompatibleDriver(provider.base_url, api_key, model.name, **_capabilities(provider, model))

    capabilities = _capabilities(provider, model)
    if template.driver == "anthropic":
        driver = AnthropicDriver(provider.base_url, api_key, model.name)
    elif template.driver == "gemini":
        driver = GeminiDriver(provider.base_url, api_key, model.name)
    else:
        return OpenAICompatibleDriver(provider.base_url, api_key, model.name, **capabilities)
    driver.supports_tools = capabilities["supports_tools"]
    driver.supports_reasoning = capabilities["supports_reasoning"]
    driver.supports_vision = capabilities["supports_vision"]
    return driver
