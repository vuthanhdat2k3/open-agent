from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    runtime: str = "local"
