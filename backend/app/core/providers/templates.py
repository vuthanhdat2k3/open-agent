from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.providers.constants import DEFAULT_CONTEXT_WINDOW

DriverKey = Literal["openai_compatible", "anthropic", "gemini"]


@dataclass(frozen=True)
class FallbackModelSpec:
    name: str
    display_name: str
    context_window: int = DEFAULT_CONTEXT_WINDOW
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    supports_tools: bool | None = None
    supports_reasoning: bool | None = None
    supports_vision: bool | None = None


@dataclass(frozen=True)
class ProviderTemplate:
    key: str
    display_name: str
    description: str
    driver: DriverKey
    default_base_url: str
    api_key_required: bool
    supports_tools: bool
    supports_reasoning: bool
    supports_vision: bool
    catalog_source: str
    catalog_version: str
    fallback_models: tuple[FallbackModelSpec, ...]


_TEMPLATES: tuple[ProviderTemplate, ...] = (
    ProviderTemplate(
        key="openai",
        display_name="OpenAI",
        description="OpenAI API with chat completions and model discovery.",
        driver="openai_compatible",
        default_base_url="https://api.openai.com/v1",
        api_key_required=True,
        supports_tools=True,
        supports_reasoning=True,
        supports_vision=True,
        catalog_source="openai-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("gpt-4o-mini", "GPT-4o mini", 128000),
            FallbackModelSpec("gpt-4o", "GPT-4o", 128000),
        ),
    ),
    ProviderTemplate(
        key="openrouter",
        display_name="OpenRouter",
        description="Multi-provider OpenAI-compatible routing API.",
        driver="openai_compatible",
        default_base_url="https://openrouter.ai/api/v1",
        api_key_required=True,
        supports_tools=True,
        supports_reasoning=True,
        supports_vision=True,
        catalog_source="openrouter-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("openai/gpt-4o-mini", "GPT-4o mini", 128000),
            FallbackModelSpec("anthropic/claude-3.5-sonnet", "Claude 3.5 Sonnet", 200000),
        ),
    ),
    ProviderTemplate(
        key="ollama",
        display_name="Ollama",
        description="Local Ollama server through its OpenAI-compatible API.",
        driver="openai_compatible",
        default_base_url="http://localhost:11434/v1",
        api_key_required=False,
        supports_tools=True,
        supports_reasoning=False,
        supports_vision=False,
        catalog_source="ollama-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("llama3.1", "Llama 3.1", 131072),
            FallbackModelSpec("qwen2.5", "Qwen 2.5", 32768),
        ),
    ),
    ProviderTemplate(
        key="gemini",
        display_name="Google Gemini",
        description="Native Google Gemini Generative Language API.",
        driver="gemini",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_required=True,
        supports_tools=True,
        supports_reasoning=True,
        supports_vision=True,
        catalog_source="gemini-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("gemini-2.0-flash", "Gemini 2.0 Flash", 1048576),
            FallbackModelSpec("gemini-1.5-pro", "Gemini 1.5 Pro", 2097152),
        ),
    ),
    ProviderTemplate(
        key="anthropic",
        display_name="Anthropic",
        description="Native Anthropic Messages API.",
        driver="anthropic",
        default_base_url="https://api.anthropic.com",
        api_key_required=True,
        supports_tools=True,
        supports_reasoning=True,
        supports_vision=True,
        catalog_source="anthropic-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("claude-sonnet-4-20250514", "Claude Sonnet 4", 200000),
            FallbackModelSpec("claude-3-5-haiku-latest", "Claude 3.5 Haiku", 200000),
        ),
    ),
    ProviderTemplate(
        key="opencode",
        display_name="OpenCode Zen",
        description="OpenCode Zen's OpenAI-compatible coding model gateway.",
        driver="openai_compatible",
        default_base_url="https://opencode.ai/zen/v1",
        api_key_required=True,
        supports_tools=True,
        supports_reasoning=True,
        supports_vision=False,
        catalog_source="opencode-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("big-pickle", "Big Pickle", 128000),
            FallbackModelSpec("kimi-k2.5", "Kimi K2.5", 262144),
        ),
    ),
    ProviderTemplate(
        key="deepseek",
        display_name="DeepSeek",
        description="DeepSeek's OpenAI-compatible API.",
        driver="openai_compatible",
        default_base_url="https://api.deepseek.com/v1",
        api_key_required=True,
        supports_tools=True,
        supports_reasoning=True,
        supports_vision=False,
        catalog_source="deepseek-fallback-v1",
        catalog_version="1",
        fallback_models=(
            FallbackModelSpec("deepseek-chat", "DeepSeek Chat", 65536),
            FallbackModelSpec("deepseek-reasoner", "DeepSeek Reasoner", 65536, supports_reasoning=True),
        ),
    ),
)


def get_templates() -> tuple[ProviderTemplate, ...]:
    return _TEMPLATES


def get_template(key: str) -> ProviderTemplate | None:
    return next((template for template in _TEMPLATES if template.key == key), None)
