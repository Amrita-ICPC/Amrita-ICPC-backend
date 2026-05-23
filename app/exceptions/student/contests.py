"""Student-facing contest exceptions.

Re-exports contest exceptions with student-specific context.
"""

from app.exceptions.contest import ContestNotFoundError
from app.exceptions.base import AppBaseException
from fastapi import status


class NoContestTeamMemberFoundError(AppBaseException):
    """Raised when a user is not a member of any team in the contest."""
    def __init__(self, detail: str = "User is not a member of any team in this contest."):
        super().__init__(
            message=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


__all__ = [
    "ContestNotFoundError",
    "NoContestTeamMemberFoundError",
]

