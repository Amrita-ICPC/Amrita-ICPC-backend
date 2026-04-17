"""
Data Transfer Objects for student contest operations.

These DTOs bridge the repository layer and service layer, providing type-safe
data transfer without exposing ORM models directly. They represent the minimal
data needed for student-facing queries and operations.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.utils.enums import ContestStatus


@dataclass
class StudentContestFilters:
    """Filters for querying contests from a student's perspective."""

    search_term: str | None = None
    status: ContestStatus | None = None
    is_public: bool | None = None
    only_registered: bool = (
        False  # If True, only show contests student is registered in
    )
    only_available: bool = (
        False  # If True, only show contests available for registration
    )
    difficulty_level: str | None = (
        None  # Filter by problem difficulty: EASY, MEDIUM, HARD
    )


@dataclass
class StudentAvailableContestData:
    """
    Data transfer object representing an available contest for student listing.

    Encapsulates contest information that students see in the available contests list:
    - Basic details (name, description, image)
    - Dates (start, end, registration window)
    - Team configuration (min/max size, approval mode)
    - Status visibility information

    This DTO is used internally to pass data from repository to service/mapper layer.
    """

    id: UUID
    name: str
    description: str | None
    image: str | None
    start_time: datetime
    end_time: datetime
    registration_start: datetime | None
    registration_end: datetime | None
    status: ContestStatus
    is_public: bool
    problem_count: int
    min_team_size: int
    max_team_size: int
    team_approval_mode: str  # TeamApprovalMode enum value


@dataclass
class StudentRegisteredContestData:
    """
    Data transfer object representing a registered contest for student.

    Includes information about when/how student registered plus contest details.
    Used for the registered contests list view.
    """

    id: UUID
    name: str
    description: str | None
    image: str | None
    start_time: datetime
    end_time: datetime
    registration_start: datetime | None
    registration_end: datetime | None
    status: ContestStatus
    is_public: bool
    problem_count: int
    min_team_size: int
    max_team_size: int
    team_approval_mode: str
    # Registration specific fields
    registered_at: datetime
    registered_as_individual: bool
    team_id: UUID | None
    team_name: str | None


@dataclass
class StudentContestDetailData:
    """
    Data transfer object for complete contest details from student perspective.

    Includes all contest information plus problem list and student's current status.
    """

    id: UUID
    name: str
    description: str | None
    image: str | None
    start_time: datetime
    end_time: datetime
    registration_start: datetime | None
    registration_end: datetime | None
    status: ContestStatus
    is_public: bool
    rules: str | None
    min_team_size: int
    max_team_size: int
    team_approval_mode: str
    show_leaderboard: bool
    # Student registration status
    is_student_registered: bool
    student_team_id: UUID | None
    # Problems (flat list, will be mapped to problem responses)
    problems: list[dict] | None = (
        None  # [{id, order, title, difficulty, score, duration}, ...]
    )


@dataclass
class StudentContestProblemData:
    """
    Data transfer object for a single problem in a contest.

    Minimal representation of problem information visible to students.
    """

    id: UUID
    order: int
    title: str
    difficulty: str  # EASY, MEDIUM, HARD
    score: int
    duration: int
