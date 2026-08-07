from __future__ import annotations

from typing import Any

from app.customer_intelligence.mcp import call_customer_intelligence_mcp


class McpDriveProvider:
    def __init__(self, credentials: dict[str, Any] | None = None):
        self._credentials = credentials or {}

    async def _call(self, tool: str, **args: Any) -> Any:
        return await call_customer_intelligence_mcp(
            tool,
            {"access_token": self._credentials.get("access_token", ""), **args},
        )

    async def list_files(self, query: str = "", page_size: int = 20) -> list[dict[str, Any]]:
        return await self._call("drive_list_files", query=query, page_size=page_size)

    async def get_file(self, file_id: str, max_chars: int = 50000) -> dict[str, Any]:
        return await self._call("drive_get_file", file_id=file_id, max_chars=max_chars)

    async def create_file(self, name: str, content: str, mime_type: str = "text/plain", parent_id: str = "") -> dict[str, Any]:
        return await self._call("drive_create_file", name=name, content=content, mime_type=mime_type, parent_id=parent_id)

    async def update_file(self, file_id: str, content: str = "", name: str = "", mime_type: str = "text/plain") -> dict[str, Any]:
        return await self._call("drive_update_file", file_id=file_id, content=content, name=name, mime_type=mime_type)

    async def delete_file(self, file_id: str) -> dict[str, Any]:
        return await self._call("drive_delete_file", file_id=file_id)

    def bind(self, credentials: dict[str, Any]) -> McpDriveProvider:
        return type(self)(credentials)
