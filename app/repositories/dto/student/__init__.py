"""Student-facing DTOs for contests, teams, and code execution."""

from app.repositories.dto.student.contests import (
    StudentContestFilters,
)
from app.repositories.dto.student.run import (
    StudentCodeRunRequestDTO,
    StudentCodeRunResponseDTO,
    StudentTestCaseRunResultDTO,
)
from app.repositories.dto.student.teams import (
    StudentAvailableTeamData,
    StudentCreateTeamData,
    StudentTeamData,
    StudentTeamFilters,
    StudentTeamJoinData,
    StudentTeamMemberData,
    StudentTeamRegistrationData,
)

__all__ = [
    # Contest DTOs
    "StudentContestFilters",
    # Run DTOs
    "StudentCodeRunRequestDTO",
    "StudentCodeRunResponseDTO",
    "StudentTestCaseRunResultDTO",
    # Team DTOs
    "StudentTeamFilters",
    "StudentTeamMemberData",
    "StudentTeamData",
    "StudentAvailableTeamData",
    "StudentTeamRegistrationData",
    "StudentCreateTeamData",
    "StudentTeamJoinData",
]
