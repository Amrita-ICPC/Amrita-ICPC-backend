"""Schemas for student API requests/responses."""

from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class StudentPublicContestResponse(BaseModel):
    """Response model for public contest from student perspective."""

    id: UUID
    name: str
    description: str | None = None
    image: str | None = None
    start_time: datetime
    end_time: datetime
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    max_teams: int | None = None
    min_team_size: int
    max_team_size: int
    is_public: bool

    model_config = ConfigDict(from_attributes=True)


class StudentRegisteredContestResponse(BaseModel):
    """Response for contests student is registered in."""

    id: UUID
    name: str
    description: str | None = None
    status: str  # DRAFT, SCHEDULED, RUNNING, etc.
    start_time: datetime
    end_time: datetime
    team_id: UUID | None = None  # Team student is in
    team_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StudentContestRegistrationRequest(BaseModel):
    """Request to register in a contest."""

    team_name: str = Field(..., min_length=1, max_length=100)
    team_description: str | None = Field(None, max_length=500)
    member_emails: list[str] = Field(
        default_factory=list,
        description="List of team member emails (optional)"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentContestRegistrationResponse(BaseModel):
    """Response after registering in contest."""

    team_id: UUID
    team_name: str
    contest_id: UUID
    contest_name: str
    message: str

    model_config = ConfigDict(from_attributes=True)