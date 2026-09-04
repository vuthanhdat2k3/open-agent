from unittest.mock import MagicMock, patch

import pytest

from app.channels.discord_driver import DiscordDriver
from app.channels.telegram_driver import TelegramDriver


class TestTelegramDriver:
    def test_parse_webhook_text_message(self):
        driver = TelegramDriver("fake-token", {})
        payload = {
            "update_id": 123,
            "message": {
                "message_id": 42,
                "from": {"id": 111, "first_name": "Test", "is_bot": False},
                "chat": {"id": 222, "type": "private"},
                "date": 1234567890,
                "text": "Hello bot",
            },
        }

        import asyncio
        result = asyncio.run(driver.parse_webhook(payload))

        assert result is not None
        assert result.channel == "telegram"
        assert result.sender_id == "111"
        assert result.sender_name == "Test"
        assert result.conversation_id == "222"
        assert result.text == "Hello bot"
        assert result.message_type == "text"
        assert result.metadata["message_id"] == 42

    def test_parse_webhook_callback_query(self):
        driver = TelegramDriver("fake-token", {})
        payload = {
            "update_id": 123,
            "callback_query": {
                "id": "cq-1",
                "from": {"id": 111, "first_name": "User"},
                "message": {"message_id": 55, "chat": {"id": 222}},
                "data": "button_clicked",
            },
        }

        import asyncio
        result = asyncio.run(driver.parse_webhook(payload))

        assert result is not None
        assert result.channel == "telegram"
        assert result.text == "button_clicked"
        assert result.message_type == "callback_query"

    def test_parse_webhook_ignores_non_message_updates(self):
        driver = TelegramDriver("fake-token", {})
        payload = {"update_id": 123, "edited_message": {"message_id": 1}}

        import asyncio
        result = asyncio.run(driver.parse_webhook(payload))
        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_chunks_long_content(self):
        driver = TelegramDriver("fake-token", {})
        # Generate 7500 chars with paragraphs
        content = "Para 1: " + ("T" * 3500) + "\n\nPara 2: " + ("U" * 3500)

        posted_payloads = []

        class DummyResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True, "result": {"message_id": f"tg-{len(posted_payloads)}"}}

        async def fake_post(url, json=None, timeout=None):
            posted_payloads.append(json)
            return DummyResponse()

        mock_client = MagicMock()
        mock_client.post = fake_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            last_id = await driver.send_message(
                recipient="tg-chat-1",
                content=content,
                reply_to_message_id=999,
            )

        assert len(posted_payloads) == 2
        for p in posted_payloads:
            assert len(p["text"]) <= 4000
        # reply_to_message_id on first chunk
        assert posted_payloads[0]["reply_to_message_id"] == 999
        assert "reply_to_message_id" not in posted_payloads[1]
        assert last_id == "tg-2"



class TestDiscordDriver:
    def test_parse_webhook_ping_returns_none(self):
        driver = DiscordDriver("fake-token", {})
        payload = {"type": 1}

        import asyncio
        result = asyncio.run(driver.parse_webhook(payload))
        assert result is None

    def test_parse_webhook_slash_command(self):
        driver = DiscordDriver("fake-token", {})
        payload = {
            "type": 2,
            "id": "interaction-1",
            "guild_id": "guild-123",
            "channel_id": "chan-456",
            "member": {"user": {"id": "user-789", "username": "testuser"}},
            "data": {
                "id": "cmd-1",
                "name": "ask",
                "options": [{"name": "question", "value": "What is AI?"}],
            },
        }

        import asyncio
        result = asyncio.run(driver.parse_webhook(payload))

        assert result is not None
        assert result.channel == "discord"
        assert result.sender_id == "user-789"
        assert result.sender_name == "testuser"
        assert result.conversation_id == "chan-456"
        assert result.text == "/ask What is AI?"
        assert result.message_type == "slash_command"
        assert result.metadata["command_name"] == "ask"

    def test_parse_webhook_component_interaction(self):
        driver = DiscordDriver("fake-token", {})
        payload = {
            "type": 3,
            "id": "interaction-2",
            "channel_id": "chan-456",
            "member": {"user": {"id": "user-789", "username": "testuser"}},
            "data": {
                "custom_id": "btn_confirm",
                "component_type": 2,
            },
            "message": {"id": "msg-99"},
        }

        import asyncio
        result = asyncio.run(driver.parse_webhook(payload))

        assert result is not None
        assert result.channel == "discord"
        assert result.text == "btn_confirm"
        assert result.message_type == "component_interaction"
        assert result.metadata["custom_id"] == "btn_confirm"

    @pytest.mark.asyncio
    async def test_send_message_chunks_long_content(self):
        driver = DiscordDriver("fake-token", {})
        # Generate 3500 chars of text with paragraphs
        content = "Paragraph 1: " + ("A" * 1500) + "\n\nParagraph 2: " + ("B" * 1500)

        posted_payloads = []

        class DummyResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"id": f"msg-{len(posted_payloads)}"}

        async def fake_post(url, json=None, headers=None, timeout=None):
            posted_payloads.append(json)
            return DummyResponse()

        mock_client = MagicMock()
        mock_client.post = fake_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            last_id = await driver.send_message(
                recipient="chan-123",
                content=content,
                embeds=[{"title": "Test"}],
            )

        assert len(posted_payloads) == 2
        # Ensure every chunk is <= 1900 chars
        for p in posted_payloads:
            assert len(p["content"]) <= 1900
        # Embeds attached only to the final chunk
        assert "embeds" not in posted_payloads[0]
        assert posted_payloads[1]["embeds"] == [{"title": "Test"}]
        assert last_id == "msg-2"

    @pytest.mark.asyncio
    async def test_send_message_extracts_error_body(self):
        import httpx
        driver = DiscordDriver("fake-token", {})

        req = httpx.Request("POST", "https://discord.com/api/v10/channels/123/messages")
        res = httpx.Response(400, request=req, text='{"content": ["Must be 2000 or fewer in length."]}')

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPStatusError("Client error 400", request=req, response=res)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError) as exc_info:
                await driver.send_message(recipient="chan-123", content="hello")

            assert "400" in str(exc_info.value)
            assert "Must be 2000 or fewer in length." in str(exc_info.value)


class TestSplitMessage:
    def test_split_empty_or_whitespace(self):
        from app.channels.driver import split_message
        assert split_message("") == ["(Không có nội dung phản hồi)"]
        assert split_message("   \n\t  ") == ["(Không có nội dung phản hồi)"]

    def test_split_short_message(self):
        from app.channels.driver import split_message
        assert split_message("Hello world", max_length=1900) == ["Hello world"]

    def test_split_preserves_paragraphs(self):
        from app.channels.driver import split_message
        p1 = "First paragraph: " + ("1" * 1000)
        p2 = "Second paragraph: " + ("2" * 1000)
        text = f"{p1}\n\n{p2}"

        chunks = split_message(text, max_length=1900)
        assert len(chunks) == 2
        assert chunks[0] == p1
        assert chunks[1] == p2
        assert all(len(c) <= 1900 for c in chunks)

    def test_split_hard_limit_exceeded(self):
        from app.channels.driver import split_message
        # Long unbroken string
        text = "X" * 4500
        chunks = split_message(text, max_length=1900)
        assert len(chunks) == 3
        assert all(len(c) <= 1900 for c in chunks)
        assert "".join(chunks) == text

