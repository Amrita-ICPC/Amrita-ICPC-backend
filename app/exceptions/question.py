from uuid import UUID

from fastapi import status

from app.exceptions.base import AppBaseException


class QuestionNotFoundError(AppBaseException):
    """Exception raised when a requested question doesn't exist."""

    def __init__(self, question_id: str | UUID):
        super().__init__(
            message=f"Question with ID {question_id} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidQuestionError(AppBaseException):
    """Exception raised when question data fails domain validation."""

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid question data: {message}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class QuestionPermissionError(AppBaseException):
    """Exception raised when a user lacks permission for a question operation."""

    def __init__(self, message: str = "Permission denied for this question"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )
