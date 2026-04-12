"""
Student-facing contest schemas for API responses.

These schemas expose limited information compared to instructor schemas,
hiding implementation details like scoring rules, instructor assignments, etc.
Students see only what is necessary for contest participation.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import ContestStatus, TeamApprovalMode


class StudentContestRegistrationRequest(BaseModel):
    """Schema for registering a student to a contest (POST /students/contests/{id}/register)."""

    team_id: UUID = Field(
        ..., description="ID of the team to register with for this contest"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentContestProblemResponse(BaseModel):
    """Schema for a single problem in a contest (student view)."""

    id: UUID = Field(..., description="Problem unique identifier")
    order: int = Field(..., description="Problem position (1, 2, 3...)")
    title: str = Field(..., description="Problem title/name")
    difficulty: str = Field(..., description="Problem difficulty (EASY, MEDIUM, HARD)")
    score: int = Field(..., description="Points for solving this problem")
    duration: int = Field(..., description="Time limit in seconds")

    model_config = ConfigDict(from_attributes=True)


class StudentContestAvailableResponse(BaseModel):
    """Schema for contest summary in availability list (GET /students/contests/available)."""

    id: UUID = Field(..., description="Contest unique identifier")
    name: str = Field(..., description="Contest name")
    description: Optional[str] = Field(None, description="Contest description")
    image: Optional[str] = Field(None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: datetime = Field(..., description="Contest end time (UTC)")
    registration_start: Optional[datetime] = Field(
        None, description="Registration start time (UTC)"
    )
    registration_end: Optional[datetime] = Field(
        None, description="Registration end time (UTC)"
    )
    status: ContestStatus = Field(..., description="Contest status (DRAFT, SCHEDULED, RUNNING, FINISHED)")
    is_public: bool = Field(..., description="Whether contest is publicly visible")
    problem_count: int = Field(..., description="Number of problems in contest")
    team_approval_mode: TeamApprovalMode = Field(
        ..., description="How teams are approved (AUTO_APPROVE or INSTRUCTOR_REVIEW)"
    )
    min_team_size: int = Field(..., description="Minimum team size required")
    max_team_size: int = Field(..., description="Maximum team size allowed")

    model_config = ConfigDict(from_attributes=True)


class StudentContestDetailsResponse(BaseModel):
    """Schema for full contest details (GET /students/contests/{id}/details)."""

    id: UUID = Field(..., description="Contest unique identifier")
    name: str = Field(..., description="Contest name")
    description: Optional[str] = Field(None, description="Contest description")
    image: Optional[str] = Field(None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: datetime = Field(..., description="Contest end time (UTC)")
    registration_start: Optional[datetime] = Field(
        None, description="Registration start time (UTC)"
    )
    registration_end: Optional[datetime] = Field(
        None, description="Registration end time (UTC)"
    )
    status: ContestStatus = Field(..., description="Contest status")
    is_public: bool = Field(..., description="Whether contest is publicly visible")
    rules: Optional[str] = Field(None, description="Contest rules and guidelines")
    team_approval_mode: TeamApprovalMode = Field(
        ..., description="How teams are approved"
    )
    min_team_size: int = Field(..., description="Minimum team size")
    max_team_size: int = Field(..., description="Maximum team size")
    show_leaderboard: bool = Field(..., description="Whether leaderboard is visible to students")
    problems: List[StudentContestProblemResponse] = Field(
        default_factory=list, description="List of problems in contest"
    )
    student_registered: bool = Field(
        ..., description="Whether current student is registered for this contest"
    )
    student_team_id: Optional[UUID] = Field(
        None, description="Team ID if student is already registered with a team"
    )

    model_config = ConfigDict(from_attributes=True)


class StudentContestRegistrationResponse(BaseModel):
    """Schema for contest registration response (POST /students/contests/{id}/register)."""

    message: str = Field(..., description="Registration status message")
    contest_id: UUID = Field(..., description="Contest ID")
    status: str = Field(..., description="Registration status (success, pending, already_registered)")

    model_config = ConfigDict(from_attributes=True)


class StudentRegisteredContestResponse(BaseModel):
    """Schema for registered contest (GET /students/contests/registered)."""

    id: UUID = Field(..., description="Contest unique identifier")
    name: str = Field(..., description="Contest name")
    description: Optional[str] = Field(None, description="Contest description")
    image: Optional[str] = Field(None, description="Contest image URL")
    start_time: datetime = Field(..., description="Contest start time (UTC)")
    end_time: datetime = Field(..., description="Contest end time (UTC)")
    registration_start: Optional[datetime] = Field(
        None, description="Registration start time (UTC)"
    )
    registration_end: Optional[datetime] = Field(
        None, description="Registration end time (UTC)"
    )
    status: ContestStatus = Field(..., description="Contest status (DRAFT, SCHEDULED, RUNNING, FINISHED)")
    is_public: bool = Field(..., description="Whether contest is publicly visible")
    problem_count: int = Field(..., description="Number of problems in contest")
    team_approval_mode: TeamApprovalMode = Field(
        ..., description="How teams are approved (AUTO_APPROVE or INSTRUCTOR_REVIEW)"
    )
    min_team_size: int = Field(..., description="Minimum team size required")
    max_team_size: int = Field(..., description="Maximum team size allowed")
    registered_at: datetime = Field(..., description="When student registered for this contest")
    registered_as_team: bool = Field(..., description="Whether registered as individual or team")
    team_id: Optional[UUID] = Field(None, description="Team ID if registered with team")
    team_name: Optional[str] = Field(None, description="Team name if registered with team")

    model_config = ConfigDict(from_attributes=True)


class StudentContestProblemsListResponse(BaseModel):
    """Schema for contest problems list response (GET /students/contests/{id}/problems)."""

    contest_id: UUID = Field(..., description="Contest ID")
    contest_name: str = Field(..., description="Contest name")
    problems: List[StudentContestProblemResponse] = Field(
        ..., description="List of problems in contest"
    )
    total_problems: int = Field(..., description="Total number of problems")

    model_config = ConfigDict(from_attributes=True)


class StudentContestListResponse(BaseModel):
    """Schema for paginated list of available contests (GET /students/contests/available)."""

    contests: List[StudentContestAvailableResponse] = Field(
        ..., description="List of available contests"
    )
    total: int = Field(..., description="Total number of available contests")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of contests per page")
    has_more: bool = Field(..., description="Whether there are more pages")

    model_config = ConfigDict(from_attributes=True)


class StudentRegisteredContestListResponse(BaseModel):
    """Schema for paginated list of registered contests (GET /students/contests/registered)."""

    contests: List[StudentRegisteredContestResponse] = Field(
        ..., description="List of registered contests"
    )
    total: int = Field(..., description="Total number of registered contests")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of contests per page")
    has_more: bool = Field(..., description="Whether there are more pages")

    model_config = ConfigDict(from_attributes=True)
