from enum import Enum


class Role(str, Enum):  # noqa: UP042
    """Organization roles owned by the OpenAgent authorization projection."""

    platform_admin = "platform_admin"
    org_admin = "org_admin"
    operator = "operator"
    user = "user"
