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
