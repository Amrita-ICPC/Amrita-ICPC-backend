from fastapi import status

from app.exceptions.base import AppBaseException


class EvaluationNotFoundError(AppBaseException):
    """Raised when evaluation is not found."""

    def __init__(self, evaluation_id: str):
        super().__init__(
            message=f"Evaluation with ID {evaluation_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class EvaluationBackendUnavailableError(AppBaseException):
    """Raised when evaluation backend (e.g. Redis) is unavailable."""

    def __init__(self, message: str = "Evaluation backend is unavailable") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
