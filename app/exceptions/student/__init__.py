"""Student module exceptions.

Centralized exception definitions for all student-facing endpoints.
Organizes exceptions by resource type (contests, teams, etc).

Usage:
    from app.exceptions.student.contests import ContestNotFoundError
    from app.exceptions.student.teams import TeamNotFoundError, MemberAlreadyInTeamError
"""

from app.exceptions.student.contests import ContestNotFoundError
from app.exceptions.student.teams import (
    TeamNotFoundError,
    MemberAlreadyInTeamError,
    InvalidTeamSizeError,
    TeamLeaderAccessDeniedError,
    StudentTeamNotFoundError,
    TeamMemberAccessDeniedError,
    StudentTeamUserNotFoundError,
)

__all__ = [
    "ContestNotFoundError",
    "TeamNotFoundError",
    "MemberAlreadyInTeamError",
    "InvalidTeamSizeError",
    "TeamLeaderAccessDeniedError",
    "StudentTeamNotFoundError",
    "TeamMemberAccessDeniedError",
    "StudentTeamUserNotFoundError",
]
