import uuid
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class Bank(Base):
    __tablename__ = "bank"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    questions = relationship("BankQuestion", back_populates="bank")

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
