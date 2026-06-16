from fastapi import status

from app.exceptions.base import AppBaseException


class EvaluationNotFoundError(AppBaseException):
    """Raised when evaluation is not found."""

    def __init__(self, evaluation_id: str):
        super().__init__(
            message=f"Evaluation with ID {evaluation_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
