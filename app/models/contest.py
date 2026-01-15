import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

class Contest(Base):
    __tablename__ = "contest"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    questions = relationship("ContestQuestion", back_populates="contest")
    teams = relationship("ContestTeam", back_populates="contest")

class ContestQuestion(Base):
    __tablename__ = "contest_question"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), primary_key=True
    )

    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    contest = relationship("Contest", back_populates="questions")
    question = relationship("Question", back_populates="contests")

class ContestTeam(Base):
    __tablename__ = "contest_team"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team.id", ondelete="CASCADE"), primary_key=True
    )

    score: Mapped[int] = mapped_column(Integer, default=0)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    contest = relationship("Contest", back_populates="teams")
    team = relationship("Team", back_populates="contests")
