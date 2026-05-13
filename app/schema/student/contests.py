from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from app.utils.enums import ContestMode, ContestRunStatus, ContestStatus, TeamApprovalMode
from app.schema.contest import ContestAudienceResponse

class StudentContestRegistrationRequest(BaseModel):
    registered: bool | None = None
    status: list[ContestRunStatus] | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None

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

class StudentContestDetailsResponse(BaseModel):
    """Placeholder for contest details response."""
    pass


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
