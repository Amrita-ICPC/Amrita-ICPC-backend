from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.enums import UserRole

if TYPE_CHECKING:
    from app.models.audience import UserAudience


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone_no: Mapped[str | None] = mapped_column(String(20))

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20))
    dob: Mapped[date | None]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    teams = relationship("TeamUser", back_populates="user")
    creator_bank_questions = relationship("BankQuestion", back_populates="creator")
    creator_contest_questions = relationship(
        "ContestQuestion", back_populates="creator"
    )
    deleted_banks = relationship(
        "Bank", back_populates="deleter", foreign_keys="[Bank.deleted_by]"
    )
    team_registration_members = relationship(
        "ContestTeamMember", back_populates="user", cascade="all, delete-orphan"
    )

    audience_links: Mapped[list["UserAudience"]] = relationship(
        "UserAudience",
        back_populates="user",
        cascade="all, delete-orphan",
    )
