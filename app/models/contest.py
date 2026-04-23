from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.team import Team
from app.utils.enums import (
    ContestMode,
    ContestStatus,
    ScoringType,
    TeamApprovalMode,
    TeamApprovalStatus,
    TeamStatus,
    ViolationSeverity,
    ViolationType,
)

if TYPE_CHECKING:
    from app.models.audience import ContestAudience


class Contest(Base):
    __tablename__ = "contest"
    __table_args__ = (
        CheckConstraint(
            "registration_end > registration_start", name="check_registration_window"
        ),
        CheckConstraint("end_time > start_time", name="check_contest_dates"),
        CheckConstraint("max_team_size >= min_team_size", name="check_team_size"),
        CheckConstraint(
            "(mode = 'individual' AND min_team_size = 1 AND max_team_size = 1) OR "
            "(mode = 'team')",
            name="check_mode_team_size_consistency",
        ),
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
    team_approval_mode: Mapped[TeamApprovalMode] = mapped_column(
        Enum(TeamApprovalMode, name="teamapprovalmode"),
        default=TeamApprovalMode.AUTO_APPROVE,
        nullable=False,
    )
    mode: Mapped[ContestMode] = mapped_column(
        Enum(ContestMode, name="contest_mode"),
        default=ContestMode.INDIVIDUAL,
        nullable=False,
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

    questions = relationship(
        "ContestQuestion", back_populates="contest", cascade="all, delete-orphan"
    )
    teams = relationship(
        "ContestTeam", back_populates="contest", cascade="all, delete-orphan"
    )
    instructors: Mapped[list["ContestInstructor"]] = relationship(
        "ContestInstructor", back_populates="contest", cascade="all, delete-orphan"
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

    team_violations = relationship(
        "ContestTeamViolation", back_populates="contest", cascade="all, delete-orphan"
    )

    audience_links: Mapped[list["ContestAudience"]] = relationship(
        "ContestAudience",
        back_populates="contest",
        cascade="all, delete-orphan",
    )


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
    __table_args__ = (UniqueConstraint("contest_id", "order"),)

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), primary_key=True
    )
    bank_question_id = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    contest = relationship("Contest", back_populates="questions")
    question = relationship("Question", back_populates="contests")
    creator = relationship("User", back_populates="creator_contest_questions")


class ContestTeamProgress(Base):
    """
    Model representing the progress and status of a team in a contest.

    Attributes:
        contest_id: generic-uuid foreign key to the contest.
        team_id: generic-uuid foreign key to the team.
        score: The team's score in the contest.
        is_flagged: Boolean indicating if the team is flagged for review.
        flagged_at: Timestamp when the team was flagged.
        flagged_by: generic-uuid of the user who flagged the team.
        flagged_reason: Reason for flagging the team.
        start_time: Timestamp when the team started the contest.
        end_time: Timestamp when the team finished the contest.
    """

    __tablename__ = "contest_team_progress"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Team.id, ondelete="CASCADE"), primary_key=True
    )

    score: Mapped[int] = mapped_column(Integer, default=0)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flagged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    flagged_reason: Mapped[str | None] = mapped_column(Text)

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contest_team = relationship(
        "ContestTeam",
        back_populates="progress",
        uselist=False,
        foreign_keys=[contest_id, team_id],
        primaryjoin="and_(ContestTeamProgress.contest_id==ContestTeam.contest_id, ContestTeamProgress.team_id==ContestTeam.team_id)",
    )
    flagger = relationship("User", foreign_keys=[flagged_by])


class ContestTeam(Base):
    """
    Association model representing a team's participation in a contest.

    Attributes:
        contest_id: generic-uuid foreign key to the contest.
        team_id: generic-uuid foreign key to the team.
        score: The team's score in the contest.
        enrolled_at: Timestamp when the team enrolled.
        team_status: The status of the team in the contest (e.g., DRAFT, CONFIRMED).
        is_flagged: Boolean indicating if the team is flagged for review.
        flagged_at: Timestamp when the team was flagged.
        flagged_by: generic-uuid of the user who flagged the team.
        flagged_reason: Reason for flagging the team.
    """

    __tablename__ = "contest_team"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Team.id, ondelete="CASCADE"), primary_key=True
    )

    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    team_status: Mapped[TeamStatus] = mapped_column(
        Enum(TeamStatus), nullable=False, default=TeamStatus.DRAFT, name="team_status"
    )
    approval_status: Mapped[TeamApprovalStatus] = mapped_column(
        Enum(TeamApprovalStatus, name="teamapprovalstatus"),
        nullable=False,
        default=TeamApprovalStatus.APPROVED,
    )

    contest = relationship("Contest", back_populates="teams", foreign_keys=[contest_id])
    team = relationship("Team", back_populates="team_contests", foreign_keys=[team_id])
    progress = relationship(
        "ContestTeamProgress",
        back_populates="contest_team",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[ContestTeamProgress.contest_id, ContestTeamProgress.team_id]",
        primaryjoin="and_(ContestTeam.contest_id==ContestTeamProgress.contest_id, ContestTeam.team_id==ContestTeamProgress.team_id)",
    )


class ContestTeamViolation(Base):
    """
    Model representing a violation recorded for a team in a contest.

    Attributes:
        id: Unique identifier for the violation.
        contest_id: generic-uuid foreign key to the contest.
        team_id: generic-uuid foreign key to the team.
        violation_type: Type of the violation (e.g., CHEATING).
        violation_severity: Severity of the violation (e.g., LOW, CRITICAL).
        violation_at: Timestamp when the violation occurred.
        violated_by: generic-uuid of the user who committed the violation.
        violation_reason: detailed description or reason for the violation.
    """

    __tablename__ = "contest_team_violation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Team.id, ondelete="CASCADE"), nullable=False
    )

    violation_type: Mapped[ViolationType] = mapped_column(
        Enum(ViolationType), nullable=False
    )
    violation_severity: Mapped[ViolationSeverity] = mapped_column(
        Enum(ViolationSeverity), nullable=False
    )
    violation_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    violated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    violation_reason: Mapped[str] = mapped_column(Text, nullable=False)

    contest = relationship("Contest", back_populates="team_violations")
    team = relationship("Team", back_populates="contest_violations")
    violator = relationship("User", foreign_keys=[violated_by])
