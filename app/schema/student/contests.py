from app.utils.enums import TeamMemberRole
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator
from app.utils.enums import ContestMode, ContestRunStatus, ContestStatus, TeamApprovalMode, RegistrationState
from app.schema.contest import ContestAudienceResponse

class StudentContestRegistrationRequest(BaseModel):
    registered: bool | None = None
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
    end_time: datetime = Field(..., description="Contest end time (UTC)")
    status: ContestStatus = Field(..., description="Contest lifecycle status")
    run_status: ContestRunStatus = Field(
        ..., description="Contest temporal run-state (UPCOMING / LIVE / ENDED)"
    )
    registration_start: Optional[datetime] = Field(None, description="Registration start time (UTC)")
    registration_end: Optional[datetime] = Field(None, description="Registration end time (UTC)")
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
    max_teams: Optional[int] = Field(None, description="Maximum number of teams allowed")
    teams_count: int = Field(0, description="Total number of teams registered and approved")
    min_team_size: int = Field(..., description="Minimum team size")
    max_team_size: int = Field(..., description="Maximum team size")


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


class StudentContestProblemResponse(BaseModel):
    pass

class StudentContestProblemsListResponse(BaseModel):
    pass

class StudentContestRegistrationResponse(BaseModel):
    pass

class StudentRegisteredContestListResponse(BaseModel):
    pass

class StudentRegisteredContestResponse(BaseModel):
    pass

class RegistrationStatus(BaseModel):
    """Schema for student registration status in a contest."""
    registered: bool = Field(..., description="Whether the student is registered for the contest")
    approved: bool = Field(..., description="Whether the registration is approved")
    status: RegistrationState = Field(..., description="Combined registration status (e.g., APPROVED, PENDING_APPROVAL, NOT_REGISTERED)")

class ReadinessStatus(BaseModel):
    """Schema for student readiness to start a contest."""
    can_start: bool = Field(..., description="Whether the student/team can start the contest")
    reason: Optional[str] = Field(None, description="Reason if the student/team cannot start")

class TeamMemberStatus(BaseModel):
    """Schema for team member status in participation view."""
    id: UUID = Field(..., description="User ID of the member")
    name: str = Field(..., description="Name of the member")
    role: TeamMemberRole = Field(..., description="Role in the team (LEADER / MEMBER)")
    joined: bool = Field(..., description="Whether the user has joined the team")
    confirmed: bool = Field(..., description="Whether the user has confirmed participation")

class TeamParticipationStatus(BaseModel):
    """Schema for team participation status in a contest."""
    id: UUID = Field(..., description="Team ID")
    name: str = Field(..., description="Team name")
    members: list[TeamMemberStatus] = Field(..., description="List of team members and their status")
    member_count: int = Field(..., description="Current number of members")
    min_team_size: int = Field(..., description="Minimum team size")
    max_team_size: int = Field(..., description="Maximum team size allowed")
    completion_percentage: float = Field(..., description="Percentage of team completion")

class StudentContestStatusResponse(BaseModel):
    """Combined response for student's status and participation in a contest."""
    registration_status: RegistrationStatus = Field(..., description="Registration and approval status")
    readiness: ReadinessStatus = Field(..., description="Readiness to start the contest")
    team: Optional[TeamParticipationStatus] = Field(None, description="Team details if registered")
