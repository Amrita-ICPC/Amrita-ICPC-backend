from datetime import datetime
from uuid import UUID

from app.exceptions.contest import (
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
    InvalidContestError,
)
from app.models.contest import ContestInstructor


class ContestValidator:
    """Validator for contest business rules and constraints.

    This class implements the Validator Pattern, centralizing all business rule
    validation for contest operations. It ensures data integrity and enforces
    domain-specific constraints before operations are executed.

    Responsibilities:
        - Validate contest date constraints (start/end times, registration periods)
        - Validate team size constraints (min/max)
        - Validate instructor assignment rules (individual and bulk operations)
        - Check data consistency and business rules

    Design Principles:
        - Single Responsibility: Only handles business rule validation
        - Stateless: All methods are static (no instance state)
        - Fail Fast: Raises domain exceptions immediately on violation
        - Reusable: Called by service layer before state changes

    Validation Methods:
        - validate_contest_dates: Ensures end_time > start_time
        - validate_registration_dates: Ensures valid registration period
        - validate_team_size_constraints: Enforces min <= max team size
        - validate_instructor_not_assigned: Prevents duplicate instructor assignments
        - validate_instructor_assigned: Ensures instructor exists before removal
        - validate_instructors_not_in_contest: Bulk validation for instructor assignments
        - validate_instructors_in_contest: Bulk validation for instructor removal

    Exception Strategy:
        - Raises domain-specific exceptions (InvalidContestError, etc.)
        - Provides clear error messages with context
        - Never modifies state (validation only)
    """

    @staticmethod
    def validate_contest_dates(start_time: datetime, end_time: datetime) -> None:
        """
        Validates that contest end time is after start time.

        Args:
            start_time: Contest start time
            end_time: Contest end time

        Raises:
            InvalidContestError: If end_time <= start_time
        """
        if end_time <= start_time:
            raise InvalidContestError("end_time must be after start_time")

    @staticmethod
    def validate_registration_dates(
        registration_start: datetime | None,
        registration_end: datetime | None,
        start_time: datetime | None,
    ) -> None:
        """
        Validates that registration period is valid.

        Args:
            registration_start: Registration start time
            registration_end: Registration end time
            start_time: Contest start time

        Raises:
            InvalidContestError: If registration dates are invalid
        """
        if registration_end is None or registration_start is None or start_time is None:
            raise InvalidContestError("Registration dates are required")

        if registration_end <= registration_start:
            raise InvalidContestError(
                "registration_end must be after registration_start"
            )
        if registration_end > start_time:
            raise InvalidContestError(
                "registration_end must be before or equal to contest start_time"
            )

    @staticmethod
    def validate_team_size_constraints(min_size: int, max_size: int) -> None:
        """
        Validates that team size constraints are valid.

        Args:
            min_size: Minimum team size
            max_size: Maximum team size

        Raises:
            InvalidContestError: If min_size > max_size or either is <= 0
        """
        if min_size <= 0 or max_size <= 0:
            raise InvalidContestError("Team sizes must be greater than 0")
        if min_size > max_size:
            raise InvalidContestError("min_team_size must be <= max_team_size")

    @staticmethod
    def validate_instructor_not_assigned(
        is_assigned: bool, instructor_id: UUID, contest_id: UUID
    ) -> None:
        """
        Validates that an instructor is not already assigned to a contest.

        Args:
            is_assigned: Whether the instructor is already assigned
            instructor_id: ID of the instructor
            contest_id: ID of the contest

        Raises:
            InstructorAlreadyAssignedError: If instructor is already assigned
        """
        if is_assigned:
            raise InstructorAlreadyAssignedError(str(instructor_id), str(contest_id))

    @staticmethod
    def validate_instructor_assigned(
        is_assigned: bool, instructor_id: UUID, contest_id: UUID
    ) -> None:
        """
        Validates that an instructor is assigned to a contest before removal.

        Args:
            is_assigned: Whether the instructor is assigned
            instructor_id: ID of the instructor
            contest_id: ID of the contest

        Raises:
            InstructorNotAssignedError: If instructor is not assigned
        """
        if not is_assigned:
            raise InstructorNotAssignedError(str(instructor_id), str(contest_id))

    @staticmethod
    def validate_instructors_not_in_contest(
        instructor_ids: list[UUID], new_instructor_ids: list[UUID]
    ) -> None:
        """
        Validates that the given instructors are not already assigned to the contest.

        Args:
            instructor_ids: Set of existing instructor IDs in the contest
            new_instructor_ids: Set of new instructor IDs to be added

        Raises:
            InstructorAlreadyAssignedError: If any instructor is already assigned
        """
        already_assigned = set(instructor_ids).intersection(set(new_instructor_ids))
        if already_assigned:
            raise InstructorAlreadyAssignedError(
                str(next(iter(already_assigned))), "Contest"
            )

    @staticmethod
    def validate_instructors_in_contest(
        instructor_ids: set[UUID], existing_instructor_ids: set[UUID]
    ) -> None:
        """
        Validates that the given instructors are already assigned to the contest.

        Args:
            instructor_ids: Set of instructor IDs to check for removal
            existing_instructor_ids: Set of existing instructor IDs in the contest

        Raises:
            InstructorNotAssignedError: If any instructor is not assigned
        """
        not_assigned = set(instructor_ids).difference(set(existing_instructor_ids))
        if not_assigned:
            raise InstructorNotAssignedError(str(next(iter(not_assigned))), "Contest")

    @staticmethod
    def validate_instructors_assigned(
        contest_id: UUID,
        instructor_ids: list[UUID],
        assignments: list[ContestInstructor],
    ) -> None:
        """
        Validate that all given instructors are assigned to the contest.

        Args:
            contest_id: ID of the contest
            instructor_ids: List of instructor IDs to validate
            assignments: List of ContestInstructor objects representing current assignments

        Raises:
            InstructorNotAssignedError: If any instructor is not assigned to the contest
        """
        found_instructor_ids = {assignment.instructor_id for assignment in assignments}
        missing_instructor_ids = set(instructor_ids) - found_instructor_ids

        if missing_instructor_ids:
            # Raise exception for the first missing instructor ID
            missing_id = next(iter(missing_instructor_ids))
            raise InstructorNotAssignedError(str(missing_id), str(contest_id))
