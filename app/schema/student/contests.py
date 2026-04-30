"""
Student-facing contest schemas for API responses.

These schemas expose limited information compared to instructor schemas,
hiding implementation details like scoring rules, instructor assignments, etc.
Students see only what is necessary for contest participation.

Schema Organization:
    - Request Schemas: StudentContestRegistrationRequest
    - Response Base Schemas: StudentContestProblemResponse
    - Summary Responses (List views): StudentContestAvailableResponse, StudentRegisteredContestResponse
    - Detail Responses: StudentContestDetailsResponse
    - Collection Responses: StudentContestListResponse, StudentRegisteredContestListResponse
    - Registration Responses: StudentContestRegistrationResponse, StudentContestProblemsListResponse
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import ContestStatus, TeamApprovalMode


# Request Schemas
class StudentContestRegistrationRequest(BaseModel):
    """
    Schema for registering a student/team to a contest.

    Attributes:
        team_id: ID of the team to register with for this contest
    """

    team_id: UUID = Field(
        ..., description="ID of the team to register with for this contest"
    )

    model_config = ConfigDict(from_attributes=True)


# Base Response Schemas
class StudentContestProblemResponse(BaseModel):
    """
    Schema for a single problem in a contest from student view.

    Shows only student-relevant problem information:
    - Problem metadata (title, difficulty)
    - Time and score constraints
    - Problem order in contest

    Attributes:
        id: Problem unique identifier
        order: Position in contest (1-indexed)
        title: Problem name/title
        difficulty: Difficulty level (EASY, MEDIUM, HARD)
        score: Points awarded for solving
        duration: Time limit in seconds
    """

    id: UUID = Field(..., description="Problem unique identifier")
    order: int = Field(..., description="Problem position in contest (1-indexed)")
    title: str = Field(..., description="Problem title/name")
    difficulty: str = Field(..., description="Problem difficulty (EASY, MEDIUM, HARD)")
    score: int = Field(..., description="Points awarded for solving this problem")
    duration: Optional[int] = Field(None, description="Time limit in seconds")

    model_config = ConfigDict(from_attributes=True)


# Summary Response Schemas (for list views)
class StudentContestAvailableResponse(BaseModel):
    """
    Schema for contest summary in availability list.

    Used in GET /students/contests/available endpoint.
    Shows high-level contest information for discovery.

    Attributes:
        id: Contest unique identifier
        name: Contest name
        description: Optional contest description
        image: Optional contest image URL
        start_time: Contest start time (UTC)
        end_time: Contest end time (UTC)
        registration_start: Registration window start
        registration_end: Registration window end
        status: Current contest status
        is_public: Whether contest is publicly visible
        problem_count: Number of problems in contest
        team_approval_mode: How teams are approved
        min_team_size: Minimum team size required
        max_team_size: Maximum team size allowed
    """

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
    status: ContestStatus = Field(
        ..., description="Contest status (DRAFT, SCHEDULED, RUNNING, FINISHED)"
    )
    is_public: bool = Field(..., description="Whether contest is publicly visible")
    problem_count: int = Field(..., description="Number of problems in contest")
    team_approval_mode: TeamApprovalMode = Field(
        ..., description="How teams are approved (AUTO_APPROVE or INSTRUCTOR_REVIEW)"
    )
    min_team_size: int = Field(..., description="Minimum team size required")
    max_team_size: int = Field(..., description="Maximum team size allowed")

    model_config = ConfigDict(from_attributes=True)


class StudentRegisteredContestResponse(BaseModel):
    """
    Schema for registered contest summary.

    Used in GET /students/contests/registered endpoint.
    Shows contests student is already registered in.

    Attributes:
        id: Contest unique identifier
        name: Contest name
        description: Optional contest description
        image: Optional contest image URL
        start_time: Contest start time (UTC)
        end_time: Contest end time (UTC)
        status: Current contest status
        problem_count: Number of problems in contest
        team_approval_mode: How teams are approved
        min_team_size: Minimum team size required
        max_team_size: Maximum team size allowed
        registered_at: When student registered for this contest
        registered_as_team: Whether registered as team member or individual
        team_id: Team ID if registered with team
        team_name: Team name if registered with team
    """

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
    status: ContestStatus = Field(
        ..., description="Contest status (DRAFT, SCHEDULED, RUNNING, FINISHED)"
    )
    is_public: bool = Field(..., description="Whether contest is publicly visible")
    problem_count: int = Field(..., description="Number of problems in contest")
    team_approval_mode: TeamApprovalMode = Field(
        ..., description="How teams are approved (AUTO_APPROVE or INSTRUCTOR_REVIEW)"
    )
    min_team_size: int = Field(..., description="Minimum team size required")
    max_team_size: int = Field(..., description="Maximum team size allowed")
    registered_at: datetime = Field(
        ..., description="When student registered for this contest"
    )
    registered_as_team: bool = Field(
        ..., description="Whether registered as individual or team"
    )
    team_id: Optional[UUID] = Field(None, description="Team ID if registered with team")
    team_name: Optional[str] = Field(
        None, description="Team name if registered with team"
    )

    model_config = ConfigDict(from_attributes=True)


# Detail Response Schemas
class StudentContestDetailsResponse(BaseModel):
    """
    Schema for full contest details with problems.

    Used in GET /students/contests/{id}/details endpoint.
    Comprehensive view of contest for registered or known student.

    Attributes:
        id: Contest unique identifier
        name: Contest name
        description: Contest description
        image: Contest image URL
        start_time: Contest start time (UTC)
        end_time: Contest end time (UTC)
        registration_start: Registration window start
        registration_end: Registration window end
        status: Current contest status
        is_public: Whether publicly visible
        rules: Contest rules and guidelines
        team_approval_mode: How teams are approved
        min_team_size: Minimum team size
        max_team_size: Maximum team size
        show_leaderboard: Whether leaderboard is visible to students
        problems: List of problems in contest
        student_registered: Whether current student is registered
        student_team_id: Team ID if student registered with team
    """

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
    show_leaderboard: bool = Field(
        ..., description="Whether leaderboard is visible to students"
    )
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


# Registration Response Schemas
class StudentContestRegistrationResponse(BaseModel):
    """
    Schema for contest registration operation response.

    Used in POST /students/contests/{id}/register endpoint.
    Confirms registration and provides status.

    Attributes:
        message: Registration status message
        contest_id: Contest ID
        status: Registration status (success, pending, already_registered)
    """

    message: str = Field(..., description="Registration status message")
    contest_id: UUID = Field(..., description="Contest ID")
    status: str = Field(
        ..., description="Registration status (success, pending, already_registered)"
    )

    model_config = ConfigDict(from_attributes=True)


# Collection Response Schemas
class StudentContestProblemsListResponse(BaseModel):
    """
    Schema for problems list in a specific contest.

    Used in GET /students/contests/{id}/problems endpoint.
    Returns all problems for a contest with their details.

    Attributes:
        contest_id: Contest ID
        contest_name: Contest name for context
        problems: List of problems in contest
        total_problems: Total number of problems
    """

    contest_id: UUID = Field(..., description="Contest ID")
    contest_name: str = Field(..., description="Contest name")
    problems: List[StudentContestProblemResponse] = Field(
        ..., description="List of problems in contest"
    )
    total_problems: int = Field(..., description="Total number of problems")

    model_config = ConfigDict(from_attributes=True)


class StudentContestListResponse(BaseModel):
    """
    Schema for paginated list of available contests.

    Used in GET /students/contests/available endpoint.
    Returns paginated results with navigation info.

    Attributes:
        contests: List of available contests
        total: Total number of available contests
        page: Current page number
        page_size: Number of contests per page
        has_more: Whether there are more pages
    """

    contests: List[StudentContestAvailableResponse] = Field(
        ..., description="List of available contests"
    )
    total: int = Field(..., description="Total number of available contests")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of contests per page")
    has_more: bool = Field(..., description="Whether there are more pages")

    model_config = ConfigDict(from_attributes=True)


class StudentRegisteredContestListResponse(BaseModel):
    """
    Schema for paginated list of registered contests.

    Used in GET /students/contests/registered endpoint.
    Returns contests student is already registered in.

    Attributes:
        contests: List of registered contests
        total: Total number of registered contests
        page: Current page number
        page_size: Number of contests per page
        has_more: Whether there are more pages
    """

    contests: List[StudentRegisteredContestResponse] = Field(
        ..., description="List of registered contests"
    )
    total: int = Field(..., description="Total number of registered contests")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of contests per page")
    has_more: bool = Field(..., description="Whether there are more pages")

    model_config = ConfigDict(from_attributes=True)
