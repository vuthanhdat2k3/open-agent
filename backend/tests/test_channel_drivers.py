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

    @pytest.mark.asyncio
    async def test_trigger_typing(self):
        driver = TelegramDriver("fake-token", {})
        called_urls = []

        class DummyResponse:
            status_code = 200

        async def fake_post(url, json=None, timeout=None):
            called_urls.append((url, json))
            return DummyResponse()

        mock_client = MagicMock()
        mock_client.post = fake_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            await driver.trigger_typing(recipient="tg-123")

        assert len(called_urls) == 1
        assert "sendChatAction" in called_urls[0][0]
        assert called_urls[0][1] == {"chat_id": "tg-123", "action": "typing"}

    @pytest.mark.asyncio
    async def test_edit_message(self):
        driver = TelegramDriver("fake-token", {})
        called_urls = []

        class DummyResponse:
            status_code = 200
            def json(self):
                return {"ok": True}

        async def fake_post(url, json=None, timeout=None):
            called_urls.append((url, json))
            return DummyResponse()

        mock_client = MagicMock()
        mock_client.post = fake_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            ok = await driver.edit_message(recipient="tg-123", message_id="456", content="Hello updated")

        assert ok is True
        assert len(called_urls) == 1
        assert "editMessageText" in called_urls[0][0]
        assert called_urls[0][1]["text"] == "Hello updated"




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

    @pytest.mark.asyncio
    async def test_trigger_typing(self):
        driver = DiscordDriver("fake-token", {})
        called_urls = []

        class DummyResponse:
            status_code = 204

        async def fake_post(url, headers=None, timeout=None):
            called_urls.append(url)
            return DummyResponse()

        mock_client = MagicMock()
        mock_client.post = fake_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            await driver.trigger_typing(recipient="chan-123")

        assert len(called_urls) == 1
        assert called_urls[0] == "https://discord.com/api/v10/channels/chan-123/typing"

    @pytest.mark.asyncio
    async def test_edit_message(self):
        driver = DiscordDriver("fake-token", {})
        called_patches = []

        class DummyResponse:
            status_code = 200

        async def fake_patch(url, json=None, headers=None, timeout=None):
            called_patches.append((url, json))
            return DummyResponse()

        mock_client = MagicMock()
        mock_client.patch = fake_patch
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            ok = await driver.edit_message(recipient="chan-123", message_id="msg-999", content="Streaming partial ▌")

        assert ok is True
        assert len(called_patches) == 1
        assert called_patches[0][0] == "https://discord.com/api/v10/channels/chan-123/messages/msg-999"
        assert called_patches[0][1] == {"content": "Streaming partial ▌"}


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


class TestTelegramBotManager:
    @pytest.mark.asyncio
    async def test_telegram_manager_singleton(self):
        from app.channels.gateway import TelegramBotManager, get_telegram_manager

        mgr1 = get_telegram_manager()
        mgr2 = get_telegram_manager()
        assert isinstance(mgr1, TelegramBotManager)
        assert mgr1 is mgr2

    @pytest.mark.asyncio
    async def test_telegram_bot_manager_lifecycle(self):
        from app.channels.gateway import TelegramBotManager
        from app.models.channel import ChannelConnection

        mgr = TelegramBotManager()
        fake_conn = MagicMock(spec=ChannelConnection)
        fake_conn.id = "tg-conn-1"
        fake_conn.bot_username = "test_bot"
        fake_conn.bot_token_enc = "fake_enc"

        with patch("app.channels.gateway.decrypt_string", return_value="fake_token"), \
             patch.object(mgr, "_run_bot", return_value=None):
            await mgr.add_bot(fake_conn)
            assert "tg-conn-1" in mgr._tasks

            # Adding again should be idempotent
            await mgr.add_bot(fake_conn)
            assert len(mgr._tasks) == 1

            await mgr.remove_bot("tg-conn-1")
            assert "tg-conn-1" not in mgr._tasks

            await mgr.shutdown()
            assert mgr._shutdown is True

    @pytest.mark.asyncio
    async def test_telegram_send_message_parse_mode_fallback(self):
        import httpx

        driver = TelegramDriver("fake-token", {})

        called_payloads = []

        def custom_handler(request: httpx.Request):
            import json
            data = json.loads(request.content.decode("utf-8"))
            called_payloads.append(data)
            if "parse_mode" in data:
                return httpx.Response(400, json={"ok": False, "description": "Bad Request: can't parse entities in message"})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 888}})

        transport = httpx.MockTransport(custom_handler)
        with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
            msg_id = await driver.send_message("12345", "Raw **invalid <markdown>", parse_mode="HTML")

        assert msg_id == "888"
        assert len(called_payloads) == 2
        # First attempt had parse_mode
        assert called_payloads[0].get("parse_mode") == "HTML"
        # Second attempt fell back without parse_mode
        assert "parse_mode" not in called_payloads[1]

    @pytest.mark.asyncio
    async def test_telegram_parse_webhook_photo_and_document(self):
        driver = TelegramDriver("fake-token", {})

        # 1. Photo message
        photo_payload = {
            "update_id": 200,
            "message": {
                "message_id": 99,
                "from": {"id": 111, "first_name": "PhotoUser"},
                "chat": {"id": 222, "type": "private"},
                "date": 1234567890,
                "caption": "Check this picture",
                "photo": [
                    {"file_id": "thumb-id", "file_size": 100},
                    {"file_id": "highres-id", "file_size": 25000, "width": 800, "height": 600},
                ],
            },
        }
        res_photo = await driver.parse_webhook(photo_payload)
        assert res_photo is not None
        assert res_photo.text == "Check this picture"
        assert len(res_photo.metadata["attachments"]) == 1
        att_photo = res_photo.metadata["attachments"][0]
        assert att_photo["id"] == "highres-id"
        assert att_photo["content_type"] == "image/jpeg"
        assert att_photo["size"] == 25000

        # 2. Document message
        doc_payload = {
            "update_id": 201,
            "message": {
                "message_id": 100,
                "from": {"id": 111, "first_name": "DocUser"},
                "chat": {"id": 222, "type": "private"},
                "date": 1234567890,
                "caption": "Quarterly report",
                "document": {
                    "file_id": "doc-99",
                    "file_name": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 1048576,
                },
            },
        }
        res_doc = await driver.parse_webhook(doc_payload)
        assert res_doc is not None
        assert res_doc.text == "Quarterly report"
        assert len(res_doc.metadata["attachments"]) == 1
        att_doc = res_doc.metadata["attachments"][0]
        assert att_doc["id"] == "doc-99"
        assert att_doc["name"] == "report.pdf"
        assert att_doc["content_type"] == "application/pdf"
        assert att_doc["size"] == 1048576

    @pytest.mark.asyncio
    async def test_telegram_get_file_info_and_download(self):
        import httpx

        driver = TelegramDriver("fake-token", {})

        def custom_handler(request: httpx.Request):
            if "getFile" in str(request.url):
                return httpx.Response(
                    200,
                    json={"ok": True, "result": {"file_id": "highres-id", "file_path": "photos/file_1.jpg", "file_size": 4}},
                )
            if "file/botfake-token/photos/file_1.jpg" in str(request.url):
                return httpx.Response(200, content=b"\xff\xd8\xff\xe0")
            return httpx.Response(404)

        transport = httpx.MockTransport(custom_handler)
        mock_client = httpx.AsyncClient(transport=transport)
        TelegramDriver._shared_clients[driver.base_url] = mock_client
        info = await driver.get_file_info("highres-id")
        assert info is not None
        assert info["file_path"] == "photos/file_1.jpg"

        file_bytes = await driver.download_file_bytes("photos/file_1.jpg")
        assert file_bytes == b"\xff\xd8\xff\xe0"

    def test_discord_markdown_table_and_heading_formatting(self):
        from app.channels.formatters import convert_markdown

        raw_text = (
            "#### Thông tin cơ bản\n\n"
            "| Tiêu chí | Nội dung |\n"
            "|----------|----------|\n"
            "| Tên văn bản | Sắc lệnh Số 109 |\n"
            "| **Ngày ban hành** | 18 tháng 6 năm 1946 |\n\n"
            "##### Cấp bậc & Chức danh\n\n"
            "| Cấp bậc | Mô tả | Ghi chú |\n"
            "|---|---|---|\n"
            "| **Cấp 1-3** | Toàn màu vàng | Nhân viên |\n"
        )

        formatted = convert_markdown(raw_text, "discord")

        # Headings level 4+ should be converted to ###
        assert "####" not in formatted
        assert "#####" not in formatted
        assert "### Thông tin cơ bản" in formatted
        assert "### Cấp bậc & Chức danh" in formatted

        # Tables should be converted to clean bullet lists with bold keys, not raw pipes or code blocks
        assert "|----------|" not in formatted
        assert "• **Tên văn bản:** Sắc lệnh Số 109" in formatted
        assert "• **Ngày ban hành:** 18 tháng 6 năm 1946" in formatted
        # Multi-column table
        assert "• **Cấp 1-3:** Mô tả: Toàn màu vàng — Ghi chú: Nhân viên" in formatted




