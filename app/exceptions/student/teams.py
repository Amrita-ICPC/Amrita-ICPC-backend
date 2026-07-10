"""Student-facing team exceptions.

Re-exports team exceptions with student-specific context.
"""

from app.exceptions.base import AppBaseException
from app.exceptions.team import (
    InvalidTeamSizeError,
    MemberAlreadyInTeamError,
    StudentTeamInvitationError,
    StudentTeamInvitationNotFoundError,
    StudentTeamNotFoundError,
    StudentTeamUserNotFoundError,
    TeamLeaderAccessDeniedError,
    TeamMemberAccessDeniedError,
    TeamNotFoundError,
)


class TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException(AppBaseException):
    """Raised when team status is not allowed for updating contest team member status."""

    error_code = "TEAM_STATUS_NOT_ALLOWED_FOR_UPDATING_CONTEST_TEAM_MEMBER_STATUS"

    def __init__(
        self,
        detail: str = "Updating contest team member status is not allowed because the team status does not permit this operation.",
    ):
        super().__init__(
            message=detail,
            status_code=400,
            detail=detail,
        )


class InvalidContestTeamMemberStatusUpdateException(AppBaseException):
    """Raised when the contest team member status update is invalid."""

    error_code = "INVALID_CONTEST_TEAM_MEMBER_STATUS_UPDATE"

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
