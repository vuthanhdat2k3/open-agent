class ChannelError(Exception):
    """Base exception for channel operations."""


class ChannelConnectionError(ChannelError):
    """Raised when a channel connection fails."""


class ChannelWebhookError(ChannelError):
    """Raised when webhook processing fails."""


class ChannelNotConfiguredError(ChannelError):
    """Raised when required channel configuration is missing."""
