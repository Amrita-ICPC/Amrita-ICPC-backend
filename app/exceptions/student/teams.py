"""Student-facing team exceptions.

Re-exports team exceptions with student-specific context.
"""

from app.exceptions.team import (
    TeamNotFoundError,
    MemberAlreadyInTeamError,
    InvalidTeamSizeError,
    TeamLeaderAccessDeniedError,
    StudentTeamNotFoundError,
    StudentTeamInvitationNotFoundError,
    StudentTeamInvitationError,
    TeamMemberAccessDeniedError,
    StudentTeamUserNotFoundError,
)

__all__ = [
    "TeamNotFoundError",
    "MemberAlreadyInTeamError",
    "InvalidTeamSizeError",
    "TeamLeaderAccessDeniedError",
    "StudentTeamNotFoundError",
    "StudentTeamInvitationNotFoundError",
    "StudentTeamInvitationError",
    "TeamMemberAccessDeniedError",
    "StudentTeamUserNotFoundError",
]

