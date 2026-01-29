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


class KeycloakSyncError(AppBaseException):
    """Raised when Keycloak user synchronization fails."""

    def __init__(self, message: str = "Failed to synchronize Keycloak users"):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class UnauthorizedSyncError(AppBaseException):
    """Raised when non-admin user attempts to sync Keycloak users."""

    def __init__(self, message: str = "Only administrators can sync Keycloak users"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )
