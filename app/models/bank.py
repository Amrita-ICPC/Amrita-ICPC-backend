import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
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
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
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

    bank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), primary_key=True
    )

    bank = relationship("Bank", back_populates="questions")
    question = relationship("Question", back_populates="banks")
