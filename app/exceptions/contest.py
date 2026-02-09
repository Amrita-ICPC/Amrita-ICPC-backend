from fastapi import status

from app.exceptions.base import AppBaseException


class ContestNotFoundError(AppBaseException):
    """Raised when contest is not found."""

    def __init__(self, contest_id: str):
        super().__init__(
            message=f"Contest with ID {contest_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ContestAlreadyExistsError(AppBaseException):
    """Raised when contest with same name already exists."""

    def __init__(self, name: str):
        super().__init__(
            message=f"Contest with name '{name}' already exists",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidContestError(AppBaseException):
    """Raised when contest data is invalid."""

    def __init__(self, message: str = "Invalid contest data"):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ContestOperationError(AppBaseException):
    """Raised when contest operation fails."""

    def __init__(self, message: str = "Contest operation failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
