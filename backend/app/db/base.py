from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import DeclarativeBase


def gen_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass
