import uuid
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase


def gen_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    # Models use TIMESTAMP WITHOUT TIME ZONE. Persist naive UTC consistently
    # across SQLite and PostgreSQL, and only attach a timezone at API boundaries.
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass
