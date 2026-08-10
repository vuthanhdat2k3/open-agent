from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderBase(BaseModel):
    key: str
    name: str
    base_url: str
    api_key: str = ""
    env_var: str = ""
    is_default: bool = False


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(BaseModel):
    key: str | None = None
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    env_var: str | None = None
    is_default: bool | None = None
    clear_api_key: bool = False


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    name: str
    base_url: str
    env_var: str
    is_default: bool
    template_key: str | None = None
    api_key_configured: bool
    api_key_last4: str | None = None
    status: str
    discovery_status: str
    discovery_error: str | None = None
    models_discovered: int
    last_discovery_attempt_at: datetime | None = None
    last_successful_discovery_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProviderFromTemplateRequest(BaseModel):
    template_key: str = Field(min_length=1)
    api_key: str = ""
    base_url: str | None = None
    is_default: bool = False


class ProviderTemplateOut(BaseModel):
    key: str
    display_name: str
    description: str
    driver: str
    default_base_url: str
    api_key_required: bool
    supports_tools: bool
    supports_reasoning: bool
    supports_vision: bool
    catalog_source: str
    catalog_version: str


class ProviderTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model_count: int
    message: str
    status: str = "ready"
    discovery_status: str = "pending"
    discovery_error: str | None = None
    models_discovered: int = 0
