from fastapi import status

from app.exceptions.base import AppBaseException


class UserNotFoundError(AppBaseException):
    """Raised when user is not found."""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"User with ID {user_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidUserError(AppBaseException):
    """Raised when user data is invalid."""

    def __init__(self, message: str = "Invalid user data"):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class UserAlreadyExistsError(AppBaseException):
    """Raised when user already exists."""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"User with ID {user_id} already exists",
            status_code=status.HTTP_409_CONFLICT,
        )
