from datetime import datetime
from typing import Optional

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
    key: Optional[str] = None
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    env_var: Optional[str] = None
    is_default: Optional[bool] = None


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
