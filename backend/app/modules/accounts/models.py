# Tables owned by the accounts module (AD-1, AD-4, AD-5).
# users and sessions are global; memberships belong to one Business (tenant table).
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.repository import TenantModel


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    email: Mapped[str] = mapped_column(unique=True)  # stored lowercased
    password_hash: Mapped[str]  # Argon2id hash only, never the password
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    # Named UserSession so it is not confused with SQLAlchemy's Session. Used from Story 2.2.
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(TenantModel):
    __tablename__ = "memberships"
    __table_args__ = (
        # Lets other tenant tables point here with a (business_id, id) foreign key (AD-3).
        UniqueConstraint("business_id", "id"),
        CheckConstraint(
            "cardinality(roles) > 0 AND roles <@ ARRAY['owner','staff','technician']::text[]",
            name="roles_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)
    # unique: one Business per user in the MVP (AD-4).
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text))
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
