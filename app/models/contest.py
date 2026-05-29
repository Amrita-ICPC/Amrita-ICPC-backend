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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.team import Team
from app.models.user import User
from app.utils.enums import (
    ContestMode,
    ContestRuntimeStatus,
    ContestStatus,
    ContestTeamMemberStatus,
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
            "(contest_mode = 'individual' AND min_team_size = 1 AND max_team_size = 1) OR "
            "(contest_mode = 'team')",
            name="check_mode_team_size_consistency",
        ),
        CheckConstraint(
            "duration IS NULL OR duration <= EXTRACT(EPOCH FROM (end_time - start_time))",
            name="check_duration_less_than_contest_length",
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
    contest_mode: Mapped[ContestMode] = mapped_column(
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

    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    team_members: Mapped[list["ContestTeamMember"]] = relationship(
        "ContestTeamMember", back_populates="contest", cascade="all, delete-orphan"
    )

    progress: Mapped[list["ContestTeamProgress"]] = relationship(
        "ContestTeamProgress", back_populates="contest", cascade="all, delete-orphan"
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


# TODO: Add a next_question_order field, to behave that field as counter
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

    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    contest = relationship("Contest", back_populates="questions")
    question = relationship("Question", back_populates="contests")
    creator = relationship("User", back_populates="creator_contest_questions")


class ContestRuntime(Base):
    __tablename__ = "contest_runtime"

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )
    runtime_status: Mapped[ContestRuntimeStatus] = mapped_column(
        Enum(ContestRuntimeStatus, name="contest_run_time_status"),
        nullable=False,
        default=ContestRuntimeStatus.SCHEDULED,
    )

    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_paused_duration: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scoreboard_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_user: Mapped["User"] = relationship(
        "User", lazy="joined", foreign_keys=[updated_by]
    )


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
    __table_args__ = (UniqueConstraint("contest_id", "contest_team_id"),)
    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), primary_key=True
    )

    contest_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest_team.id", ondelete="CASCADE"), primary_key=True
    )

    # Scoring related fields
    score: Mapped[int] = mapped_column(Integer, default=0)
    penalty: Mapped[int] = mapped_column(Integer, default=0)
    solved_questions_count: Mapped[int] = mapped_column(Integer, default=0)

    # Flagging related fields
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flagged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    flagged_reason: Mapped[str | None] = mapped_column(Text)

    # Time related fields
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_time_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Editor field
    current_editor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    current_editor_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[current_editor_user_id],
        lazy="selectin",
    )

    contest_team = relationship("ContestTeam", back_populates="progress", uselist=False)

    contest = relationship("Contest", back_populates="progress")

    # User relationships
    flagger = relationship("User", foreign_keys=[flagged_by])

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


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
    __table_args__ = (
        Index(
            "uq_contest_team_contest_id_team_id",
            "contest_id",
            "team_id",
            unique=True,
            postgresql_where=text(
                "approval_status IN ('WAITING', 'APPROVED') OR team_status IN ('DRAFT', 'CONFIRMED')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE")
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(Team.id, ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    leader_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    leader = relationship("User", foreign_keys=[leader_id])
    contest_team_member: Mapped[list["ContestTeamMember"]] = relationship(
        "ContestTeamMember", back_populates="contest_team", cascade="all, delete-orphan"
    )
    progress = relationship(
        "ContestTeamProgress",
        back_populates="contest_team",
        cascade="all, delete-orphan",
    )


class ContestTeamMember(Base):
    __tablename__ = "contest_team_member"

    __table_args__ = (
        Index(
            "uq_contest_team_member_team_user",
            "contest_team_id",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('ACCEPTED', 'INVITED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest.id", ondelete="CASCADE"), nullable=False
    )
    contest_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contest_team.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[ContestTeamMemberStatus] = mapped_column(
        Enum(ContestTeamMemberStatus),
        nullable=False,
        default=ContestTeamMemberStatus.INVITED,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contest = relationship("Contest", back_populates="team_members")
    contest_team: Mapped[ContestTeam] = relationship(
        "ContestTeam",
        back_populates="contest_team_member",
        foreign_keys=[contest_team_id],
    )
    user = relationship("User", back_populates="team_registration_members")


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
