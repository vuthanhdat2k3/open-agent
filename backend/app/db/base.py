import uuid
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase


def gen_id() -> str:
    # Langfuse v4 trace IDs are 32 lowercase hexadecimal characters. New run
    # IDs therefore remain UUIDv4 values while also mapping 1:1 to trace IDs.
    return uuid.uuid4().hex


def utc_now() -> datetime:
    # Models use TIMESTAMP WITHOUT TIME ZONE. Persist naive UTC consistently
    # across SQLite and PostgreSQL, and only attach a timezone at API boundaries.
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass
