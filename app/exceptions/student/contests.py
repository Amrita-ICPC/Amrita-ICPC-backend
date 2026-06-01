"""Student-facing contest exceptions.

Re-exports contest exceptions with student-specific context.
"""

from fastapi import status

from app.exceptions.base import AppBaseException
from app.exceptions.contest import ContestNotFoundError


class NoContestTeamMemberFoundError(AppBaseException):
    """Raised when a user is not a member of any team in the contest."""

    def __init__(
        self, detail: str = "User is not a member of any team in this contest."
    ):
        super().__init__(
            message=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class ContestSessionNotStartedError(AppBaseException):
    """Raised when a user attempts to read/access a session that has not started yet."""

    def __init__(self, detail: str = "Contest session has not started yet."):
        super().__init__(
            message=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


__all__ = [
    "ContestNotFoundError",
    "NoContestTeamMemberFoundError",
    "ContestSessionNotStartedError",
]
