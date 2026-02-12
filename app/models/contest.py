import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.enums import ContestStatus, ScoringType


class Contest(Base):
    __tablename__ = "contest"
    __table_args__ = (
        CheckConstraint(
            "registration_end > registration_start", name="check_registration_window"
        ),
        CheckConstraint("end_time > start_time", name="check_contest_dates"),
        CheckConstraint("max_team_size >= min_team_size", name="check_team_size"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Students related information
    max_teams: Mapped[int | None] = mapped_column(Integer, default=None)
    min_team_size: Mapped[int] = mapped_column(Integer, default=1)
    max_team_size: Mapped[int] = mapped_column(Integer, default=1)
    rules: Mapped[str | None] = mapped_column(Text, default=None)
    registration_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registration_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scoring_type: Mapped[ScoringType] = mapped_column(
        Enum(ScoringType, name="scoringtype"), default=ScoringType.AUTO
    )

    # Publishing related details
    status: Mapped[ContestStatus] = mapped_column(
        Enum(ContestStatus), default=ContestStatus.DRAFT
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    publisher = relationship("User", foreign_keys=[published_by])
    show_leaderboard: Mapped[bool] = mapped_column(Boolean, default=False)

    # recovery
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    deleter = relationship("User", foreign_keys=[deleted_by])

    contest_teams = relationship("Team", back_populates="contest")
    questions = relationship("ContestQuestion", back_populates="contest")
    teams = relationship("ContestTeam", back_populates="contest")
    instructors: Mapped[list["ContestInstructor"]] = relationship(
        "ContestInstructor", back_populates="contest"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    creator = relationship("User", lazy="joined", foreign_keys=[created_by])
    updater = relationship("User", lazy="joined", foreign_keys=[updated_by])


class ContestInstructor(Base):
    __tablename__ = "contest_instructor"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    contest = relationship("Contest", back_populates="instructors")
    instructor = relationship("User", foreign_keys=[instructor_id])


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
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    contest = relationship("Contest", back_populates="teams")
    team = relationship("Team", back_populates="contests")
