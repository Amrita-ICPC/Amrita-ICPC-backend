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
