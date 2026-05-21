from fastapi import status

from app.exceptions.base import AppBaseException


class ContestNotFoundError(AppBaseException):
    """Raised when contest is not found."""

    def __init__(self, contest_id: str):
        super().__init__(
            message=f"Contest with ID {contest_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ContestDeletedError(AppBaseException):
    """Raised when contest is soft-deleted."""

    def __init__(self, contest_id: str):
        super().__init__(
            message=f"Contest with ID {contest_id} has been deleted",
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


class InstructorNotFoundError(AppBaseException):
    """Raised when instructor is not found."""

    def __init__(self, instructor_id: str):
        super().__init__(
            message=f"Instructor with ID {instructor_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InstructorAlreadyAssignedError(AppBaseException):
    """Raised when instructor is already assigned to contest."""

    def __init__(self, instructor_id: str, contest_id: str):
        super().__init__(
            message=f"Instructor {instructor_id} is already assigned to contest {contest_id}",
            status_code=status.HTTP_409_CONFLICT,
        )


class InstructorNotAssignedError(AppBaseException):
    """Raised when instructor is not assigned to contest."""

    def __init__(self, instructor_id: str, contest_id: str):
        super().__init__(
            message=f"Instructor {instructor_id} is not assigned to contest {contest_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidInstructorRoleError(AppBaseException):
    """Raised when user is not an instructor."""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"User {user_id} is not an instructor",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class QuestionAlreadyInContestError(AppBaseException):
    """Raised when question is already added to the contest."""

    def __init__(self, question_id: str, contest_id: str):
        super().__init__(
            message=f"Question {question_id} is already in contest {contest_id}",
            status_code=status.HTTP_409_CONFLICT,
        )


class QuestionNotInContestError(AppBaseException):
    """Raised when question is not found in the contest."""

    def __init__(self, question_id: str, contest_id: str):
        super().__init__(
            message=f"Question {question_id} is not in contest {contest_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidContestQuestionDataError(AppBaseException):
    """Raised when contest question data is invalid."""

    def __init__(self, message: str = "Invalid contest question data"):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class DuplicateQuestionOrderError(AppBaseException):
    """Raised when question order conflicts with existing questions."""

    def __init__(self, order: int, contest_id: str):
        super().__init__(
            message=f"Question order {order} already exists in contest {contest_id}",
            status_code=status.HTTP_409_CONFLICT,
        )


class AudienceNotAssignedToContestError(AppBaseException):
    """Raised when audience is not assigned to contest."""

    def __init__(self, audience_id: str, contest_id: str):
        super().__init__(
            message=f"Audience {audience_id} is not assigned to contest {contest_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidContestStateError(AppBaseException):
    """Raised when contest is in an invalid state for the requested operation."""

    def __init__(self, contest_id: str, operation: str, current_status: str, required_status: str | list[str]):
        if isinstance(required_status, list):
            status_str = " or ".join(required_status)
        else:
            status_str = required_status
        message = f"Cannot {operation} contest {contest_id}. Current status: {current_status}, required: {status_str}"
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class StudentNotEligibleForContestError(AppBaseException):
    """Raised when student is not eligible for the contest."""

    def __init__(self, user_id: str, contest_id: str):
        super().__init__(
            message=f"Student {user_id} is not eligible for contest {contest_id}",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class StudentAlreadyInContestError(AppBaseException):
    """Raised when student is already registered or enrolled in the contest."""

    def __init__(self, user_id: str, contest_id: str):
        super().__init__(
            message=f"Student {user_id} is already in contest {contest_id}",
            status_code=status.HTTP_409_CONFLICT,
        )


class TeamAlreadyInContestError(AppBaseException):
    """Raised when team is already registered or enrolled in the contest."""

    def __init__(self, team_id: str, contest_id: str):
        super().__init__(
            message=f"Team {team_id} is already in contest {contest_id}",
            status_code=status.HTTP_409_CONFLICT,
        )

