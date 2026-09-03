from __future__ import annotations

import pytest

from app.channels.telegram_driver import TelegramDriver
from app.channels.discord_driver import DiscordDriver


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
