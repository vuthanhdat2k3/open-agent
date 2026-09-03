from __future__ import annotations

from app.channels.driver import ChannelDriver
from app.models.channel import ChannelConnection


def build_channel_driver(connection: ChannelConnection) -> ChannelDriver:
    """Build a ChannelDriver from a ChannelConnection."""
    provider = connection.provider
    from app.core.credential_secrets import decrypt_string

    token = decrypt_string(connection.bot_token_enc)

    if provider == "telegram":
        from app.channels.telegram_driver import TelegramDriver

        return TelegramDriver(token, connection.config or {})
    elif provider == "discord":
        from app.channels.discord_driver import DiscordDriver

        return DiscordDriver(token, connection.config or {})
    else:
        raise ValueError(f"Unsupported channel provider: {provider}")
