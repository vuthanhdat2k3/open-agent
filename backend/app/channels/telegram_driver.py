from __future__ import annotations

import logging
from typing import Any

import httpx

from app.channels.driver import InboundMessage, TestResult, split_message

logger = logging.getLogger(__name__)


class TelegramDriver:
    """Telegram Bot API driver using direct HTTP calls.

    Uses the Telegram Bot API for sending messages and parsing webhooks.
    Does not require aiogram as a dependency - uses httpx for HTTP calls.
    """

    _shared_clients: dict[str, httpx.AsyncClient] = {}

    def __init__(self, bot_token: str, config: dict[str, Any]) -> None:
        self.token = bot_token
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    @classmethod
    def _get_http_client(cls, base_url: str) -> httpx.AsyncClient:
        client = cls._shared_clients.get(base_url)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0,
                ),
            )
            cls._shared_clients[base_url] = client
        return client

    @property
    def client(self) -> httpx.AsyncClient:
        return self._get_http_client(self.base_url)

    async def send_message(
        self,
        recipient: str,
        content: str,
        **opts: Any,
    ) -> str:
        """Send a message to a Telegram chat with HTML formatting.

        Automatically splits messages longer than 4000 characters into sequential
        chunks to prevent Telegram HTTP 400 (4096-character limit).
        Converts markdown to Telegram HTML for rich formatting.
        """
        from app.channels.formatters import convert_markdown

        # Convert markdown to Telegram HTML
        content = convert_markdown(content, "telegram")

        chunks = split_message(content, max_length=4000)
        last_id = ""

        client = self.client
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": recipient,
                "text": chunk,
            }
            # Default to HTML parse_mode unless explicitly disabled
            parse_mode = opts.get("parse_mode", "HTML")
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if i == 0 and opts.get("reply_to_message_id"):
                payload["reply_to_message_id"] = opts["reply_to_message_id"]
            if opts.get("disable_web_page_preview"):
                payload["disable_web_page_preview"] = opts["disable_web_page_preview"]

            try:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=30.0,
                )
                if (
                    resp.status_code == 400
                    and "parse" in resp.text.lower()
                    and "parse_mode" in payload
                ):
                    # Retry without parse_mode on entity parsing error
                    payload.pop("parse_mode", None)
                    resp = await client.post(
                        f"{self.base_url}/sendMessage",
                        json=payload,
                        timeout=30.0,
                    )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Telegram API error: {data}")
                last_id = str(data["result"]["message_id"])
            except httpx.HTTPStatusError as exc:
                err_body = ""
                try:
                    err_body = f" - Telegram response: {exc.response.text}"
                except Exception:
                    pass
                logger.error(
                    "Telegram send_message error (status %s)%s",
                    exc.response.status_code,
                    err_body,
                )
                raise RuntimeError(
                    f"Telegram API error {exc.response.status_code}{err_body}"
                ) from exc

        return last_id

    async def trigger_typing(self, recipient: str) -> None:
        """Trigger typing chat action in a Telegram chat."""
        try:
            await self.client.post(
                f"{self.base_url}/sendChatAction",
                json={"chat_id": recipient, "action": "typing"},
                timeout=10.0,
            )
        except Exception as e:
            logger.debug("telegram_trigger_typing_failed: %s", e)

    async def edit_message(
        self,
        recipient: str,
        message_id: str,
        content: str,
        **opts: Any,
    ) -> bool:
        """Edit an existing Telegram message for progressive live streaming."""
        from app.channels.formatters import convert_markdown

        # Convert markdown to Telegram HTML
        content = convert_markdown(content, "telegram")

        chunks = split_message(content, max_length=4000)
        target_content = chunks[0] if chunks else content

        payload: dict[str, Any] = {
            "chat_id": recipient,
            "message_id": int(message_id) if str(message_id).isdigit() else message_id,
            "text": target_content,
        }
        # Default to HTML parse_mode unless explicitly disabled
        parse_mode = opts.get("parse_mode", "HTML")
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            client = self.client
            resp = await client.post(
                f"{self.base_url}/editMessageText",
                json=payload,
                timeout=15.0,
            )
            if (
                resp.status_code == 400
                and "parse" in resp.text.lower()
                and "parse_mode" in payload
            ):
                payload.pop("parse_mode", None)
                resp = await client.post(
                    f"{self.base_url}/editMessageText",
                    json=payload,
                    timeout=15.0,
                )
            data = resp.json()
            return bool(data.get("ok"))
        except Exception as e:
            logger.debug("telegram_edit_message_failed: %s", e)
            return False

    async def get_file_info(self, file_id: str) -> dict[str, Any] | None:
        """Get file path and details from Telegram Bot API."""
        try:
            resp = await self.client.get(
                f"{self.base_url}/getFile",
                params={"file_id": file_id},
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result")
        except Exception as e:
            logger.warning("telegram_get_file_info_failed: %s", e)
        return None

    async def download_file_bytes(self, file_path: str) -> bytes | None:
        """Download raw binary content of a file from Telegram."""
        try:
            url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            resp = await self.client.get(url, timeout=45.0)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.warning("telegram_download_file_bytes_failed: %s", e)
        return None

    async def parse_webhook(self, payload: dict[str, Any]) -> InboundMessage | None:
        """Parse a Telegram Update into an InboundMessage."""
        # Handle callback queries
        if "callback_query" in payload:
            cq = payload["callback_query"]
            message = cq.get("message", {})
            return InboundMessage(
                channel="telegram",
                sender_id=str(cq["from"]["id"]),
                sender_name=cq["from"].get("first_name", ""),
                conversation_id=str(message.get("chat", {}).get("id", "")),
                text=cq.get("data", ""),
                raw=payload,
                message_type="callback_query",
                metadata={"message_id": message.get("message_id")},
            )

        # Handle regular messages
        message = payload.get("message")
        if message is None:
            return None

        # Extract text or caption
        text = message.get("text") or message.get("caption") or ""

        # Extract attachments (photos, documents, audio)
        attachments: list[dict[str, Any]] = []

        # Photos: Telegram sends an array of sizes, pick the highest resolution
        if "photo" in message and isinstance(message["photo"], list) and message["photo"]:
            best_photo = message["photo"][-1]
            file_id = best_photo.get("file_id")
            if file_id:
                attachments.append({
                    "id": file_id,
                    "type": "image",
                    "file_id": file_id,
                    "name": f"telegram_photo_{file_id[-8:]}.jpg",
                    "size": best_photo.get("file_size", 0),
                    "mime_type": "image/jpeg",
                    "content_type": "image/jpeg",
                })

        # Documents: PDF, DOCX, CSV, code, etc.
        if "document" in message and isinstance(message["document"], dict):
            doc = message["document"]
            file_id = doc.get("file_id")
            if file_id:
                mime_type = doc.get("mime_type", "application/octet-stream")
                is_img = mime_type.startswith("image/")
                attachments.append({
                    "id": file_id,
                    "type": "image" if is_img else "document",
                    "file_id": file_id,
                    "name": doc.get("file_name", f"document_{file_id[-8:]}"),
                    "size": doc.get("file_size", 0),
                    "mime_type": mime_type,
                    "content_type": mime_type,
                })

        if not text and attachments:
            text = "Vui lòng xem và phân tích (các) tệp đính kèm này."

        if not text and not attachments:
            return InboundMessage(
                channel="telegram",
                sender_id=str(message["from"]["id"]),
                sender_name=message["from"].get("first_name", ""),
                conversation_id=str(message["chat"]["id"]),
                text="",
                raw=payload,
                message_type="non_text",
                metadata={"message_type": next(
                    (k for k, v in message.items() if k not in ("from", "chat", "date", "message_id")),
                    "unknown"
                )},
            )

        return InboundMessage(
            channel="telegram",
            sender_id=str(message["from"]["id"]),
            sender_name=message["from"].get("first_name", ""),
            conversation_id=str(message["chat"]["id"]),
            text=text,
            raw=payload,
            message_type="text",
            reply_to=str(message.get("reply_to_message", {}).get("message_id")) if message.get("reply_to_message") else None,
            metadata={
                "message_id": message.get("message_id"),
                "chat_type": message["chat"].get("type"),
                "attachments": attachments,
            },
        )

    async def setup_webhook(self, url: str, secret_token: str | None = None) -> None:
        """Set webhook URL on Telegram with optional secret token for authentication."""
        payload: dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        resp = await self.client.post(
            f"{self.base_url}/setWebhook",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Failed to set webhook: {data}")

    async def test_connection(self) -> TestResult:
        """Verify the bot token is valid."""
        try:
            resp = await self.client.get(
                f"{self.base_url}/getMe",
                timeout=10.0,
            )
            data = resp.json()
            if data.get("ok"):
                bot_info = data["result"]
                return TestResult(
                    ok=True,
                    message=f"@{bot_info.get('username', 'unknown')}",
                )
            return TestResult(ok=False, message=data.get("description", "Unknown error"))
        except httpx.HTTPError as e:
            return TestResult(ok=False, message=f"HTTP error: {e}")
        except Exception as e:
            return TestResult(ok=False, message=str(e))
