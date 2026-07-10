from fastapi import status

from app.exceptions.base import AppBaseException


class AudienceNotFoundError(AppBaseException):
    """Raised when an audience is not found."""

    def __init__(self, audience_id: str):
        super().__init__(
            message=f"Audience with ID {audience_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class AudienceAlreadyExistsError(AppBaseException):
    """Raised when attempting to create/update an audience with a duplicate name."""

    def __init__(self, name: str):
        super().__init__(
            message=f"Audience with name '{name}' already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class UserNotInAudienceError(AppBaseException):
    """Raised when a user is not part of an audience."""

    error_code = "USER_NOT_IN_AUDIENCE"

    def __init__(self, user_id: str, audience_ids: list[str] | None = None):
        super().__init__(
            message=f"User {user_id} is not a member of the requested audience(s)",
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"user_id": user_id, "audience_ids": audience_ids}
            if audience_ids
            else None,
        )
