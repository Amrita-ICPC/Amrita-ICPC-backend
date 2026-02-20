import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.enums import UserRole


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
        DateTime(timezone=True), default=datetime.utcnow
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    teams = relationship("TeamUser", back_populates="user")
    creator_bank_questions = relationship("BankQuestion", back_populates="creator")
    creator_contest_questions = relationship(
        "ContestQuestion", back_populates="creator"
    )
    deleted_banks = relationship(
        "Bank", back_populates="deleter", foreign_keys="[Bank.deleted_by]"
    )
