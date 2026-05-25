"""
Data Transfer Objects for student contest operations.

These DTOs bridge the repository layer and service layer, providing type-safe
data transfer without exposing ORM models directly. They represent the minimal
data needed for student-facing queries and operations.
"""

from dataclasses import dataclass

from app.utils.enums import ContestRunStatus, ContestStatus


@dataclass
class StudentContestFilters:
    """Filters for querying contests from a student's perspective."""

    search_term: str | None = None
    status: ContestStatus | None = None
    run_statuses: list[ContestRunStatus] | None = None
    registered: bool | None = None
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
    min_team_size: int | None = None
    max_team_size: int | None = None

