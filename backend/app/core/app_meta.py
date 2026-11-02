# The app_meta table (small key/value facts) and the function that reads the hello value.
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base

HELLO_KEY = "hello"


class AppMeta(Base):
    __tablename__ = "app_meta"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    key: Mapped[str] = mapped_column(unique=True)
    value: Mapped[str]


def get_hello_value(session: Session) -> str:
    # Read only. No commit here: the request's transaction is owned by get_session (AD-15).
    # scalar_one() raises if the row is missing or duplicated, which is what we want.
    statement = select(AppMeta.value).where(AppMeta.key == HELLO_KEY)
    return session.execute(statement).scalar_one()
