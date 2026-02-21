import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.enums import BankPermission


class Bank(Base):
    __tablename__ = "bank"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    deleter = relationship(
        "User", back_populates="deleted_banks", foreign_keys=[deleted_by]
    )

    __table_args__ = (
        UniqueConstraint("name", "created_by", name="uk_bank_name_created_by"),
    )

    questions = relationship(
        "BankQuestion", back_populates="bank", cascade="all, delete-orphan"
    )
    shares = relationship(
        "BankShare", back_populates="bank", cascade="all, delete-orphan"
    )


class BankShare(Base):
    __tablename__ = "bank_share"

    bank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[BankPermission] = mapped_column(
        Enum(BankPermission), nullable=False, default=BankPermission.read
    )

    bank = relationship("Bank", back_populates="shares")
    user = relationship("User")


class BankQuestion(Base):
    __tablename__ = "bank_question"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    bank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank.id", ondelete="CASCADE")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    creator = relationship("User", back_populates="creator_bank_questions")
    bank = relationship("Bank", back_populates="questions")
    question = relationship("Question", back_populates="banks")

    __table_args__ = (
        UniqueConstraint("bank_id", "question_id", name="uk_bank_question_pair"),
    )
