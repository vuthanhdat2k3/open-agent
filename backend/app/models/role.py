from enum import Enum


class Role(str, Enum):  # noqa: UP042
    owner = "owner"
    admin = "admin"
    developer = "developer"
    viewer = "viewer"
