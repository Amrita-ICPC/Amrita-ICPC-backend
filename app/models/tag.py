import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.question import Question


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    questions: Mapped[list["QuestionTag"]] = relationship(
        "QuestionTag",
        back_populates="tag",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class QuestionTag(Base):
    __tablename__ = "question_tag"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    question: Mapped["Question"] = relationship("Question", back_populates="tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="questions")
