from uuid import UUID

from fastapi import status

from app.exceptions.base import AppBaseException


class SubmissionNotFoundError(AppBaseException):
    """Raised when a submission cannot be found."""

    error_code = "SUBMISSION_NOT_FOUND"

    def __init__(self, submission_id: str | UUID):
        super().__init__(
            message=f"Submission with ID {submission_id} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidSubmissionScoreError(AppBaseException):
    """Raised when a manually-entered submission score fails validation."""

    error_code = "INVALID_SUBMISSION_SCORE"

    def __init__(self, score: int, max_score: int):
        super().__init__(
            message=(
                f"Score must be between 0 and {max_score} for this question, got {score}."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
