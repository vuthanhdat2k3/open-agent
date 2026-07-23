from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class ProviderOut(ProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class ProviderTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model_count: int
    message: str
