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


class Judge0ServiceError(AppBaseException):
    """Exception raised when Judge0 integration fails."""

    def __init__(self, message: str = "Unable to fetch languages from Judge0"):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class CodeStorageError(AppBaseException):
    """Exception raised when code payload storage operations fail."""

    def __init__(self, message: str = "Unable to persist code payload"):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class LanguageConflictError(AppBaseException):
    """Exception raised when platform language conflicts on unique fields."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class LanguageNotFoundError(AppBaseException):
    """Exception raised when a requested platform language doesn't exist."""

    def __init__(self, language_id: int):
        super().__init__(
            message=f"Language with ID {language_id} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class TemplateAlreadyExistsError(AppBaseException):
    """Exception raised when a template for a language already exists in a question."""

    def __init__(self, question_id: str | UUID, language_id: int):
        super().__init__(
            message=f"Template for language {language_id} already exists for question {question_id}.",
            status_code=status.HTTP_409_CONFLICT,
        )


class TagNotFoundError(AppBaseException):
    """Exception raised when a requested tag doesn't exist."""

    def __init__(self, tag_id: str | UUID):
        super().__init__(
            message=f"Tag with ID {tag_id} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class TagAlreadyExistsError(AppBaseException):
    """Exception raised when a tag with the same name already exists."""

    def __init__(self, name: str):
        super().__init__(
            message=f"Tag with name '{name}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
