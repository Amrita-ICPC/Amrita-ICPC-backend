from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import ContestStatus, ScoringType, TeamApprovalMode


class ContestBase(BaseModel):
    """Base schema for contest with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Contest name")
    description: Optional[str] = Field(
        None, max_length=5000, description="Contest description"
    )
    image: Optional[str] = Field(None, description="Contest image URL")
    is_public: bool = Field(default=False, description="Whether contest is public")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: datetime = Field(..., description="Contest end time (UTC)")
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
    team_approval_mode: Optional[TeamApprovalMode] = Field(
        None,
        description="How teams are approved in this contest",
    )
    show_leaderboard: Optional[bool] = Field(
        None, description="Whether to show leaderboard"
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


class ContestSummaryResponse(BaseModel):
    """Schema for contest summary response (List view)."""

    id: UUID = Field(..., description="Contest ID")
    name: str = Field(..., description="Contest name")
    description: Optional[str] = Field(None, description="Contest description")
    image: Optional[str] = Field(None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: datetime = Field(..., description="Contest end time (UTC)")
    status: ContestStatus = Field(..., description="Contest status")
    created_at: datetime = Field(..., description="Contest creation time (UTC)")
    is_public: bool = Field(..., description="Whether contest is public")
    team_approval_mode: TeamApprovalMode = Field(
        ...,
        description="How teams are approved in this contest",
    )

    model_config = ConfigDict(from_attributes=True)


class ContestDetailResponse(ContestBase):
    """Schema for comprehensive contest response (Detail view)."""

    id: UUID = Field(..., description="Contest ID")
    status: ContestStatus = Field(..., description="Contest status")
    created_by: UUID = Field(..., description="Creator user ID")
    creator: Optional["InstructorResponse"] = Field(None, description="Creator details")
    created_at: datetime = Field(..., description="Contest creation time (UTC)")
    updated_at: datetime = Field(..., description="Last update time (UTC)")
    updated_by: Optional[UUID] = Field(None, description="User ID who last updated")
    show_leaderboard: bool = Field(..., description="Whether leaderboard is shown")
    published_at: Optional[datetime] = Field(None, description="Published time (UTC)")
    published_by: Optional[UUID] = Field(
        None, description="User ID who published the contest"
    )

    model_config = ConfigDict(from_attributes=True)


# For backward compatibility within module if needed, or aliasing
ContestResponse = ContestDetailResponse


class MessageResponse(BaseModel):
    """Schema for message response."""

    message: str = Field(..., description="Response message")


class InstructorManageRequest(BaseModel):
    """Schema for managing instructors in a contest."""

    instructor_ids: List[UUID] = Field(
        ..., description="List of instructor IDs to assign or remove"
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
