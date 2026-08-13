from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from app.customer_intelligence.contracts import EmailAttachmentMeta, NormalizedEmail, SyncPage
from app.customer_intelligence.mcp import call_customer_intelligence_mcp


class EmailProvider(Protocol):
    provider_name: str
    async def list_new(self, cursor: str | None, max_results: int = 20) -> SyncPage: ...
    async def list_history(self, start_history_id: str, page_token: str | None = None, max_results: int = 100) -> SyncPage: ...
    async def get_history_checkpoint(self) -> str: ...
    async def get_message(self, provider_message_id: str) -> NormalizedEmail: ...
    async def search(self, *, query: str, max_results: int = 20) -> list[NormalizedEmail]: ...
    async def modify(self, *, provider_message_id: str, add_label_ids: list[str] | None = None, remove_label_ids: list[str] | None = None) -> str: ...
    async def list_labels(self) -> list[dict[str, str]]: ...
    async def create_draft(self, *, to: str, subject: str, body: str, in_reply_to: str | None = None) -> str: ...
    async def send(self, *, draft_id: str, idempotency_key: str) -> str: ...
    async def trash(self, provider_message_id: str) -> str: ...
    async def untrash(self, provider_message_id: str) -> str: ...
    async def delivery_status(self, provider_send_id: str) -> str: ...
    async def refresh_access_token(self, credentials: dict[str, Any]) -> dict[str, Any] | None: ...
    async def revoke(self, credentials: dict[str, Any]) -> None: ...
    async def watch(self, *, topic_name: str) -> dict[str, Any]: ...


class McpEmailProvider:
    def __init__(self, provider: str, credentials: dict[str, Any] | None = None):
        self.provider_name = provider
        self._credentials = credentials or {}

    def bind(self, credentials: dict[str, Any]) -> McpEmailProvider:
        return type(self)(self.provider_name, credentials)

    async def _call(self, tool: str, **args: Any) -> Any:
        return await call_customer_intelligence_mcp(
            tool,
            {"provider": self.provider_name, "access_token": self._credentials.get("access_token", ""), **args},
        )

    @staticmethod
    def _email(data: dict[str, Any]) -> NormalizedEmail:
        received = data.get("received_at")
        if isinstance(received, str):
            received = datetime.fromisoformat(received.replace("Z", "+00:00"))
        if received is not None and received.tzinfo is not None:
            received = received.astimezone(timezone.utc).replace(tzinfo=None)
        return NormalizedEmail(
            provider=data.get("provider", ""),
            provider_message_id=data.get("provider_message_id", ""),
            thread_id=data.get("thread_id"),
            sender_name=data.get("sender_name"),
            sender_email=data.get("sender_email", ""),
            sender_domain=data.get("sender_domain", ""),
            recipients=data.get("recipients", []),
            subject=data.get("subject", ""),
            body_text=data.get("body_text", ""),
            body_html=data.get("body_html"),
            attachments=[EmailAttachmentMeta(**item) for item in data.get("attachments", [])],
            received_at=received,
            headers=data.get("headers", {}),
        )

    async def list_new(self, cursor: str | None, max_results: int = 20) -> SyncPage:
        data = await self._call("email_list_new", cursor=cursor or "", max_results=max_results)
        return SyncPage([self._email(item) for item in data.get("messages", [])], data.get("new_cursor"), bool(data.get("has_more")))

    async def list_history(self, start_history_id: str, page_token: str | None = None, max_results: int = 100) -> SyncPage:
        data = await self._call(
            "email_history",
            start_history_id=start_history_id,
            page_token=page_token or "",
            max_results=max_results,
        )
        return SyncPage(
            [self._email(item) for item in data.get("messages", [])],
            data.get("new_cursor"),
            bool(data.get("has_more")),
            data.get("history_id"),
        )

    async def get_history_checkpoint(self) -> str:
        data = await self._call("email_history_checkpoint")
        checkpoint = str(data.get("history_id") or "").strip()
        if not checkpoint:
            raise RuntimeError("email provider returned no Gmail history checkpoint")
        return checkpoint

    async def get_message(self, provider_message_id: str) -> NormalizedEmail:
        return self._email(await self._call("email_get", provider_message_id=provider_message_id))

    async def search(self, *, query: str, max_results: int = 20) -> list[NormalizedEmail]:
        data = await self._call("email_search", query=query, max_results=max_results)
        return [self._email(item) for item in data.get("messages", [])]

    async def modify(self, *, provider_message_id: str, add_label_ids: list[str] | None = None, remove_label_ids: list[str] | None = None) -> str:
        data = await self._call("email_modify", provider_message_id=provider_message_id, add_label_ids=add_label_ids or [], remove_label_ids=remove_label_ids or [])
        return data.get("message_id", provider_message_id)

    async def list_labels(self) -> list[dict[str, str]]:
        return (await self._call("email_list_labels")).get("labels", [])

    async def create_draft(self, *, to: str, subject: str, body: str, in_reply_to: str | None = None) -> str:
        data = await self._call("email_create_draft", to=to, subject=subject, body=body)
        return data["draft_id"]

    async def send(self, *, draft_id: str, idempotency_key: str) -> str:
        data = await self._call("email_send", draft_id=draft_id, idempotency_key=idempotency_key)
        return data["send_id"]

    async def trash(self, provider_message_id: str) -> str:
        return (await self._call("email_trash", provider_message_id=provider_message_id)).get("message_id", provider_message_id)

    async def untrash(self, provider_message_id: str) -> str:
        return (await self._call("email_untrash", provider_message_id=provider_message_id)).get("message_id", provider_message_id)

    async def delivery_status(self, provider_send_id: str) -> str:
        return "unknown"

    async def refresh_access_token(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        from app.customer_intelligence.oauth import refresh_provider_token
        return await refresh_provider_token(self.provider_name, credentials)

    async def revoke(self, credentials: dict[str, Any]) -> None:
        from app.customer_intelligence.oauth import revoke_provider_token
        await revoke_provider_token(self.provider_name, credentials)

    async def watch(self, *, topic_name: str) -> dict[str, Any]:
        return await self._call("email_watch", topic_name=topic_name)


def get_email_provider(provider: str) -> EmailProvider:
    if provider != "gmail":
        raise ValueError(f"unsupported email provider: {provider}; only gmail is enabled")
    return McpEmailProvider(provider)


def bind_email_provider(provider: EmailProvider, credentials: dict[str, Any]) -> EmailProvider:
    bind = getattr(provider, "bind", None)
    return bind(credentials) if callable(bind) else provider
