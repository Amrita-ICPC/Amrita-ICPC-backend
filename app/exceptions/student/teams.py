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
from app.exceptions.base import AppBaseException


class TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException(AppBaseException):
    """Raised when team status is not allowed for updating contest team member status."""
    def __init__(self, detail: str = "Updating contest team member status is not allowed because the team status does not permit this operation."):
        super().__init__(
            message=detail,
            status_code=400,
            detail=detail,
        )


class InvalidContestTeamMemberStatusUpdateException(AppBaseException):
    """Raised when the contest team member status update is invalid."""
    def __init__(self, detail: str = "Invalid contest team member status update."):
        super().__init__(
            message=detail,
            status_code=400,
            detail=detail,
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
    "TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException",
    "InvalidContestTeamMemberStatusUpdateException",
]


