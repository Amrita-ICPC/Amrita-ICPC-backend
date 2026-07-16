from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from app.utils.enums import (
    ContestMode,
    ContestQuestionStatus,
    ContestRunStatus,
    ContestStatus,
    ContestTeamParticipationType,
    QuestionDifficulty,
    RegistrationState,
    TeamApprovalMode,
    TeamApprovalStatus,
    TeamMemberRole,
    TeamStatus,
)

if TYPE_CHECKING:
    from app.models.question import Question

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schema.contest import ContestAudienceResponse
from app.schema.tag import TagResponse


class StudentContestRegistrationRequest(BaseModel):
    registered: bool | None = None
    results_published: bool | None = None
    status: list[ContestRunStatus] | None = None
    min_team_size: int | None = Field(None, ge=1)
    max_team_size: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_team_size_range(self) -> "StudentContestRegistrationRequest":
        if (
            self.min_team_size is not None
            and self.max_team_size is not None
            and self.min_team_size > self.max_team_size
        ):
            raise ValueError("min_team_size cannot be greater than max_team_size")
        return self

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value):
        if value is None:
            return None

        # Single string
        if isinstance(value, str):
            return [ContestRunStatus(s.strip()) for s in value.split(",")]

        return value


class StudentContestAvailableResponse(BaseModel):
    """Schema for contest available for students (List view)."""

    id: UUID = Field(..., description="Contest ID")
    name: str = Field(..., description="Contest name")
    description: Optional[str] = Field(None, description="Contest description")
    image: Optional[str] = Field(None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: Optional[datetime] = Field(..., description="Contest end time (UTC)")
    status: ContestStatus = Field(..., description="Contest lifecycle status")
    run_status: ContestRunStatus = Field(
        ..., description="Contest temporal run-state (UPCOMING / LIVE / ENDED)"
    )
    registration_start: Optional[datetime] = Field(
        None, description="Registration start time (UTC)"
    )
    registration_end: Optional[datetime] = Field(
        None, description="Registration end time (UTC)"
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
    audiences: list[ContestAudienceResponse] = Field(
        default_factory=list, description="List of audiences linked to this contest"
    )
    max_teams: Optional[int] = Field(
        None, description="Maximum number of teams allowed"
    )
    teams_count: int = Field(
        0, description="Total number of teams registered and approved"
    )
    min_team_size: int = Field(..., description="Minimum team size")
    max_team_size: int = Field(..., description="Maximum team size")
    duration: Optional[int] = Field(None, description="Contest duration in seconds")
    show_leaderboard_during_contest: bool = Field(
        ..., description="Whether to show leaderboard during the contest"
    )
    show_leaderboard: bool = Field(
        ..., description="Whether the leaderboard is visible once results are published"
    )
    show_team_submissions: bool = Field(
        ...,
        description="Whether a team's own submissions are visible once results are published",
    )
    participation_type: ContestTeamParticipationType = Field(
        ..., description="Participation type for team contests"
    )


class StudentContestListResponse(BaseModel):
    """Paginated list of contests for students."""

    contests: list[StudentContestAvailableResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class StudentContestDetailsResponse(StudentContestAvailableResponse):
    """Placeholder for contest details response."""

    rules: Optional[str] = Field(None, description="Contest rules")
    team_approval_mode: TeamApprovalMode = Field(
        ...,
        description="How teams are approved in this contest",
    )
    status: ContestStatus = Field(..., description="Contest lifecycle status")
    results_published_at: Optional[datetime] = Field(
        None, description="Time results were published (UTC); null if unpublished"
    )


class StudentContestQuestionResponse(BaseModel):
    """Schema for a contest question in student view."""

    id: UUID = Field(..., description="The ID of the question")
    title: str = Field(..., description="The title of the question")
    status: ContestQuestionStatus = Field(
        ..., description="The status of the question (unviewed, viewed, submitted)"
    )
    max_submission: int | None = Field(
        None, description="Maximum submissions allowed for this question"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentContestQuestionsListResponse(BaseModel):
    """Schema for a list of contest questions in student view."""

    questions: list[StudentContestQuestionResponse] = Field(
        ..., description="List of questions in the contest"
    )


class StudentContestRegistrationResponse(BaseModel):
    pass


class StudentRegisteredContestListResponse(BaseModel):
    pass


class StudentRegisteredContestResponse(BaseModel):
    pass


class RegistrationStatus(BaseModel):
    """Schema for student registration status in a contest."""

    registered: bool = Field(
        ..., description="Whether the student is registered for the contest"
    )
    approved: bool = Field(..., description="Whether the registration is approved")
    status: RegistrationState = Field(
        ...,
        description="Combined registration status (e.g., APPROVED, PENDING_APPROVAL, NOT_REGISTERED)",
    )


class StudentContestSessionStatus(BaseModel):
    """Schema for student contest session status."""

    can_start: bool = Field(
        ..., description="Whether the student/team can start the contest"
    )
    reason: Optional[str] = Field(
        None, description="Reason if the student/team cannot start"
    )
    run_status: ContestRunStatus = Field(
        ..., description="The temporal run state of the contest"
    )
    already_started: bool = Field(
        ..., description="Whether the student/team has already started the session"
    )


class TeamMemberStatus(BaseModel):
    """Schema for team member status in participation view."""

    id: UUID = Field(..., description="ContestTeamMember ID of the member")
    user_id: UUID = Field(..., description="User ID of the member")
    name: str = Field(..., description="Name of the member")
    role: TeamMemberRole = Field(..., description="Role in the team (LEADER / MEMBER)")
    joined: bool = Field(..., description="Whether the user has joined the team")
    confirmed: bool = Field(
        ..., description="Whether the user has confirmed participation"
    )
    is_current_user: bool = Field(
        ..., description="Whether the user is the current user"
    )


class TeamParticipationStatus(BaseModel):
    """Schema for team participation status in a contest."""

    id: UUID = Field(..., description="Team ID")
    name: str = Field(..., description="Team name")
    members: list[TeamMemberStatus] = Field(
        ..., description="List of team members and their status"
    )
    member_count: int = Field(..., description="Current number of members")
    min_team_size: int = Field(..., description="Minimum team size")
    max_team_size: int = Field(..., description="Maximum team size allowed")
    team_status: TeamStatus = Field(..., description="Team status")
    team_approval_status: TeamApprovalStatus = Field(
        ..., description="Team approval status"
    )
    completion_percentage: float = Field(
        ..., description="Percentage of team completion"
    )
    team_id: UUID | None = Field(None, description="Team ID if registered else None")


class StudentContestStatusResponse(BaseModel):
    """Combined response for student's status and participation in a contest."""

    registration_status: RegistrationStatus = Field(
        ..., description="Registration and approval status"
    )
    session: StudentContestSessionStatus = Field(
        ..., description="Contest session status for the student"
    )
    team: Optional[TeamParticipationStatus] = Field(
        None, description="Team details if registered"
    )


class ContestSessionStartRequest(BaseModel):
    """Schema for starting or resuming a contest session."""

    contest_team_id: UUID = Field(
        ..., description="The UUID of the contest team to start/resume the session for"
    )


class StudentTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language_id: int
    starter_code: str
    solution_code: str | None = None


class StudentTestCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    input: str
    output: str
    is_hidden: bool
    weight: int
    order: int


class StudentQuestionDetailResponse(BaseModel):
    id: UUID
    title: str
    question_text: str
    difficulty: QuestionDifficulty
    time_limit_ms: int
    memory_limit_mb: int
    allowed_languages: list[str] = Field(default_factory=list)
    tags: list[TagResponse] = Field(default_factory=list)
    templates: list[StudentTemplateResponse] = Field(default_factory=list)
    testcases: list[StudentTestCaseResponse] = Field(default_factory=list)
    max_submission: int | None = Field(
        None, description="Maximum submissions allowed for this question"
    )
    is_practice: bool = Field(
        False,
        description="True when viewed after contest results were published (practice mode)",
    )

    @classmethod
    def from_question(
        cls,
        question: "Question",
        max_submission: int | None = None,
        include_solution: bool = False,
    ) -> "StudentQuestionDetailResponse":
        language_names: list[str] = []
        for mapping in getattr(question, "languages", []) or []:
            language = getattr(mapping, "language", None)
            name = getattr(language, "name", None)
            if isinstance(name, str) and name:
                language_names.append(name)

        template_items = [
            StudentTemplateResponse(
                language_id=template.language_id,
                starter_code=template.starter_code,
                solution_code=template.solution_code if include_solution else None,
            )
            for template in (getattr(question, "templates", []) or [])
        ]

        tag_items = [
            TagResponse(id=qt.tag.id, name=qt.tag.name)
            for qt in (getattr(question, "tags", []) or [])
            if getattr(qt, "tag", None)
        ]

        testcase_items = (
            [
                StudentTestCaseResponse(
                    id=tc.id,
                    input=tc.input,
                    output=tc.output,
                    is_hidden=tc.is_hidden,
                    weight=tc.weight,
                    order=tc.order,
                )
                for tc in (getattr(question, "testcases", []) or [])
            ]
            if include_solution
            else []
        )

        return cls(
            id=question.id,
            title=getattr(question, "title", "") or "Untitled Question",
            question_text=question.question_text,
            difficulty=question.difficulty,
            time_limit_ms=question.time_limit_ms,
            memory_limit_mb=question.memory_limit_mb,
            allowed_languages=list(dict.fromkeys(language_names)),
            tags=tag_items,
            templates=template_items,
            testcases=testcase_items,
            max_submission=max_submission,
            is_practice=include_solution,
        )
