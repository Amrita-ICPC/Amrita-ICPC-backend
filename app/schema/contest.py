from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import (
    AudienceType,
    ContestMode,
    ContestRunStatus,
    ContestStatus,
    ContestTeamParticipationType,
    ScoringType,
    TeamApprovalMode,
)


class ContestBase(BaseModel):
    """Base schema for contest with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Contest name")
    description: Optional[str] = Field(
        None, max_length=5000, description="Contest description"
    )
    image: Optional[str] = Field(None, description="Contest image URL")
    is_public: bool = Field(default=False, description="Whether contest is public")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: Optional[datetime] = Field(None, description="Contest end time (UTC)")
    registration_start: Optional[datetime] = Field(
        None, description="Registration start time (UTC)"
    )
    registration_end: Optional[datetime] = Field(
        None, description="Registration end time (UTC)"
    )
    max_teams: Optional[int] = Field(
        None, description="Maximum number of teams allowed"
    )
    min_team_size: int = Field(1, description="Minimum team size")
    max_team_size: int = Field(1, description="Maximum team size")
    rules: Optional[str] = Field(None, description="Contest rules")
    scoring_type: ScoringType = Field(
        default=ScoringType.AUTO, description="Scoring type"
    )
    team_approval_mode: TeamApprovalMode = Field(
        default=TeamApprovalMode.AUTO_APPROVE,
        description="How teams are approved in this contest",
    )
    contest_mode: ContestMode = Field(
        default=ContestMode.INDIVIDUAL, description="Contest mode (individual or team)"
    )
    duration: Optional[int] = Field(None, description="Contest duration in seconds")
    show_leaderboard_during_contest: bool = Field(
        default=False, description="Whether to show leaderboard during the contest"
    )
    participation_type: ContestTeamParticipationType = Field(
        default=ContestTeamParticipationType.LEADER_ONLY,
        description="Participation type for team contests",
    )
    evaluate_on_submit: bool = Field(
        default=True,
        description="Whether to evaluate submissions immediately on submit",
    )
    max_submission_per_question: Optional[int] = Field(
        None, gt=0, description="Maximum submissions allowed per question"
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValueError("End time must be after start time")

        if self.registration_start and self.registration_end:
            if self.registration_end <= self.registration_start:
                raise ValueError(
                    "Registration end time must be after registration start time"
                )

        if self.max_team_size < self.min_team_size:
            raise ValueError(
                "Maximum team size must be greater than or equal to minimum team size"
            )

        return self


class ContestCreate(ContestBase):
    """Schema for creating a contest."""

    audience_ids: list[UUID] = Field(
        default_factory=list, description="List of audience IDs to link to this contest"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestUpdate(BaseModel):
    """Schema for updating a contest."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Contest name"
    )
    description: Optional[str] = Field(
        None, max_length=5000, description="Contest description"
    )
    image: Optional[str] = Field(None, description="Contest image URL")
    is_public: Optional[bool] = Field(None, description="Whether contest is public")
    start_time: Optional[datetime] = Field(None, description="Contest start time (UTC)")
    end_time: Optional[datetime] = Field(None, description="Contest end time (UTC)")
    registration_start: Optional[datetime] = Field(
        None, description="Registration start time (UTC)"
    )
    registration_end: Optional[datetime] = Field(
        None, description="Registration end time (UTC)"
    )
    max_teams: Optional[int] = Field(
        None, description="Maximum number of teams allowed"
    )
    min_team_size: Optional[int] = Field(None, description="Minimum team size")
    max_team_size: Optional[int] = Field(None, description="Maximum team size")
    rules: Optional[str] = Field(None, description="Contest rules")
    scoring_type: Optional[ScoringType] = Field(None, description="Scoring type")
    contest_mode: Optional[ContestMode] = Field(None, description="Contest mode")
    team_approval_mode: Optional[TeamApprovalMode] = Field(
        None,
        description="How teams are approved in this contest",
    )
    duration: Optional[int] = Field(None, description="Contest duration in seconds")
    show_leaderboard_during_contest: Optional[bool] = Field(
        None, description="Whether to show leaderboard during the contest"
    )
    participation_type: Optional[ContestTeamParticipationType] = Field(
        None, description="Participation type for team contests"
    )
    evaluate_on_submit: Optional[bool] = Field(
        None, description="Whether to evaluate submissions immediately on submit"
    )
    max_submission_per_question: Optional[int] = Field(
        None, description="Maximum submissions allowed per question"
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValueError("End time must be after start time")

        if self.registration_start and self.registration_end:
            if self.registration_end <= self.registration_start:
                raise ValueError(
                    "Registration end time must be after registration start time"
                )
        return self


class ContestAudienceResponse(BaseModel):
    """Schema for audience information within a contest."""

    id: UUID = Field(..., description="Audience ID")
    name: str = Field(..., description="Audience name")
    audience_type: AudienceType = Field(..., description="Audience type")

    model_config = ConfigDict(from_attributes=True)


class ContestSummaryResponse(BaseModel):
    """Schema for contest summary response (List view)."""

    id: UUID = Field(..., description="Contest ID")
    name: str = Field(..., description="Contest name")
    description: Optional[str] = Field(None, description="Contest description")
    image: Optional[str] = Field(None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: Optional[datetime] = Field(None, description="Contest end time (UTC)")
    status: ContestStatus = Field(..., description="Contest lifecycle status")
    run_status: ContestRunStatus = Field(
        ..., description="Contest temporal run-state (UPCOMING / LIVE / ENDED)"
    )
    created_at: datetime = Field(..., description="Contest creation time (UTC)")
    is_public: bool = Field(..., description="Whether contest is public")
    team_approval_mode: TeamApprovalMode = Field(
        ...,
        description="How teams are approved in this contest",
    )
    contest_mode: ContestMode = Field(
        ..., description="Contest mode (individual or team)"
    )
    duration: Optional[int] = Field(None, description="Contest duration in seconds")
    show_leaderboard_during_contest: bool = Field(
        ..., description="Whether to show leaderboard during the contest"
    )
    participation_type: ContestTeamParticipationType = Field(
        ..., description="Participation type for team contests"
    )
    evaluate_on_submit: bool = Field(
        ..., description="Whether to evaluate submissions immediately on submit"
    )
    max_submission_per_question: Optional[int] = Field(
        None, gt=0, description="Maximum submissions allowed per question"
    )
    audiences: list[ContestAudienceResponse] = Field(
        default_factory=list, description="List of audiences linked to this contest"
    )
    question_count: int = Field(
        0, ge=0, description="Number of questions in the contest"
    )
    team_count: int = Field(
        0, ge=0, description="Number of teams in the contest (confirmed and approved)"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestDetailResponse(ContestBase):
    """Schema for comprehensive contest response (Detail view)."""

    id: UUID = Field(..., description="Contest ID")
    status: ContestStatus = Field(..., description="Contest lifecycle status")
    run_status: ContestRunStatus = Field(
        ..., description="Contest temporal run-state (UPCOMING / LIVE / ENDED)"
    )
    team_count: int = Field(0, ge=0, description="Number of teams in the contest")
    question_count: int = Field(
        0, ge=0, description="Number of questions in the contest"
    )
    submission_count: int = Field(
        0, ge=0, description="Number of submissions for contest questions"
    )
    participant_count: int = Field(
        0, ge=0, description="Number of participants (distinct users) in the contest"
    )
    created_by: UUID = Field(..., description="Creator user ID")
    creator: Optional["InstructorResponse"] = Field(None, description="Creator details")
    created_at: datetime = Field(..., description="Contest creation time (UTC)")
    updated_at: datetime = Field(..., description="Last update time (UTC)")
    updated_by: Optional[UUID] = Field(None, description="User ID who last updated")
    published_at: Optional[datetime] = Field(None, description="Published time (UTC)")
    published_by: Optional[UUID] = Field(
        None, description="User ID who published the contest"
    )
    duration: Optional[int] = Field(None, description="Contest duration in seconds")

    model_config = ConfigDict(from_attributes=True)


# For backward compatibility within module if needed, or aliasing
ContestResponse = ContestDetailResponse


class MessageResponse(BaseModel):
    """Schema for message response."""

    message: str = Field(..., description="Response message")


class InstructorManageRequest(BaseModel):
    """Schema for managing instructors in a contest."""

    instructor_ids: list[UUID] = Field(
        ..., description="List of instructor IDs to assign or remove"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestAudienceManageRequest(BaseModel):
    """Schema for managing audiences in a contest."""

    audience_ids: list[UUID] = Field(
        ..., description="List of audience IDs to assign or remove"
    )

    model_config = ConfigDict(from_attributes=True)


class InstructorResponse(BaseModel):
    """Schema for instructor response."""

    id: UUID = Field(..., description="Instructor ID")
    user_id: str = Field(..., description="Instructor user ID")
    name: str = Field(..., description="Instructor name")
    email: str = Field(..., description="Instructor email")
    phone_no: Optional[str] = Field(None, description="Instructor phone number")
    role: str = Field(..., description="Instructor role")
    gender: Optional[str] = Field(None, description="Instructor gender")
    dob: Optional[date] = Field(None, description="Instructor date of birth")
    created_at: datetime = Field(..., description="Account creation time (UTC)")

    model_config = ConfigDict(from_attributes=True)


class AddContestQuestionRequest(BaseModel):
    """Schema for a single question to add to a contest."""

    question_id: UUID = Field(..., description="Question ID to add to contest")
    order: Optional[int] = Field(
        None,
        gt=0,
        description="Position of the question in the contest (optional, 1-indexed)",
    )
    duration: Optional[int] = Field(
        None,
        gt=0,
        description="Time allocated for this question in seconds (optional)",
    )
    score: Optional[int] = Field(
        None,
        gt=0,
        description="Points awarded for solving this question (optional, defaults to 100)",
    )
    max_submission: Optional[int] = Field(
        None, description="Maximum submissions allowed for this question (optional)"
    )

    model_config = ConfigDict(from_attributes=True)


class AddContestQuestionsRequest(BaseModel):
    """Schema for adding multiple questions to a contest in batch."""

    questions: list[AddContestQuestionRequest] = Field(
        ...,
        min_length=1,
        description="List of questions to add to the contest",
    )

    model_config = ConfigDict(from_attributes=True)


class RemoveContestQuestionRequest(BaseModel):
    """Schema for removing questions from a contest."""

    question_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="List of question IDs to remove from contest",
    )

    model_config = ConfigDict(from_attributes=True)


class ContestQuestionResponse(BaseModel):
    """Schema for contest question response (detail view)."""

    question_id: UUID = Field(..., description="Question ID")
    order: int = Field(..., description="Position of the question in the contest")
    duration: int | None = Field(
        ...,
        description="Time allocated for this question in seconds",
    )
    score: int = Field(..., description="Points awarded for solving this question")
    max_submission: int | None = Field(
        ..., description="Maximum submissions allowed for this question"
    )
    created_at: datetime = Field(..., description="When question was added to contest")
    created_by: UUID = Field(..., description="User ID who added the question")

    model_config = ConfigDict(from_attributes=True)


class ReorderContestQuestionItem(BaseModel):
    """Schema for a single question reorder item."""

    question_id: UUID = Field(..., description="Question ID to reorder")
    order: int = Field(
        ..., gt=0, description="New position of the question (1-indexed)"
    )

    model_config = ConfigDict(from_attributes=True)


class ReorderContestQuestionsRequest(BaseModel):
    """Schema for reordering multiple questions in a contest."""

    reorders: list[ReorderContestQuestionItem] = Field(
        ...,
        min_length=1,
        description="List of question reorder items",
    )

    model_config = ConfigDict(from_attributes=True)


class CloneQuestionConfig(BaseModel):
    """Configuration for a specific question being cloned."""

    question_id: UUID
    score: Optional[int] = Field(None, gt=0)
    duration: Optional[int] = Field(None, gt=0)
    max_submission: Optional[int] = Field(
        None, description="Maximum submissions allowed for this question"
    )

    model_config = ConfigDict(from_attributes=True)


class ContestBankCloneRequest(BaseModel):
    """Schema for cloning questions from a bank to a contest."""

    bank_id: UUID = Field(..., description="Source bank ID")
    copy_all: bool = Field(
        default=False, description="Whether to copy all questions from the bank"
    )
    questions: Optional[list[CloneQuestionConfig]] = Field(
        None,
        description="Specific questions to copy with optional overrides (if copy_all is False)",
    )
    score: int = Field(100, gt=0, description="Default score for cloned questions")
    duration: Optional[int] = Field(
        None, gt=0, description="Default duration for cloned questions in seconds"
    )
    max_submission: Optional[int] = Field(
        None, description="Default maximum submissions allowed for cloned questions"
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_clone_selection(self) -> "ContestBankCloneRequest":
        if self.copy_all:
            if self.questions:
                raise ValueError("questions must be omitted when copy_all is true")
        elif not self.questions:
            raise ValueError(
                "questions must contain at least one item when copy_all is false"
            )
        return self


class ContestEvent(BaseModel):
    type: str
    payload: dict[str, object]


class ContestSessionValidationData(BaseModel):
    contest_team_id: UUID
    team_id: UUID | None
    contest_team_member_id: UUID
    max_submission_per_question: int | None
    evaluate_on_submit: bool
    base_end_time: datetime | None
    extra_time_seconds: int | None
