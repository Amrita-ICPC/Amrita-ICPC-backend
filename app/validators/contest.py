from datetime import UTC, datetime
from uuid import UUID

from app.exceptions.contest import (
    ContestNotFoundError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
    InvalidContestError,
    InvalidContestStateError,
    QuestionNotInContestError,
)
from app.models.contest import ContestInstructor
from app.repositories.dto.contest import UNSET, UpdateContestData
from app.utils.enums import ContestStatus

# Fields that determine how a contest's runtime/scoring model behaves.
# Changing any of these after a team/member has actually started a session
# (see ContestRepository.has_any_session_started) can silently corrupt
# already-created ContestTeamProgress rows, leaderboard aggregation, and
# submission-cap enforcement -- e.g. flipping participation_type from
# INDIVIDUAL_WORKSPACE to LEADER_ONLY orphans per-member progress rows that
# the LEADER_ONLY code path never looks at.
STRUCTURAL_CONTEST_FIELDS: tuple[str, ...] = (
    "contest_mode",
    "participation_type",
    "evaluate_on_submit",
    "shuffle_questions",
    "min_team_size",
    "max_team_size",
    "max_submission_per_question",
)


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
    def validate_contest_dates(start_time: datetime, end_time: datetime | None) -> None:
        """
        Validates that contest end time is after start time.

        Args:
            start_time: Contest start time
            end_time: Contest end time

        Raises:
            InvalidContestError: If end_time <= start_time
        """
        if end_time is not None and end_time <= start_time:
            raise InvalidContestError("end_time must be after start_time")

    @staticmethod
    def validate_registration_dates(
        registration_start: datetime | None,
        registration_end: datetime | None,
        start_time: datetime | None,
        end_time: datetime | None,
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
        if (
            registration_end is None
            or registration_start is None
            or start_time is None
            or end_time is None
        ):
            raise InvalidContestError("Registration dates are required")

        if registration_end <= registration_start:
            raise InvalidContestError(
                "registration_end must be after registration_start"
            )
        if registration_end > end_time:
            raise InvalidContestError(
                "registration_end must be before or equal to contest end_time"
            )

    @staticmethod
    def validate_registration_date_past(
        registration_start: datetime | None, registration_end: datetime | None
    ) -> None:
        if registration_start is not None:
            if datetime.now(UTC) < registration_start.astimezone(UTC):
                raise InvalidContestError("Registration has not started yet")
        if registration_end is not None:
            if datetime.now(UTC) > registration_end.astimezone(UTC):
                raise InvalidContestError("Registration has ended")

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

    @staticmethod
    def validate_question_order(order: int) -> None:
        """
        Validate that question order is a positive integer.

        Args:
            order: The order/position of the question in the contest.

        Raises:
            InvalidContestError: If order is not positive.
        """
        if order <= 0:
            raise InvalidContestError("Question order must be greater than 0")

    @staticmethod
    def validate_question_score(score: int | None) -> None:
        """
        Validate that question score is a positive integer.

        Args:
            score: The points awarded for this question.

        Raises:
            InvalidContestError: If score is not positive.
        """
        if score is not None and score <= 0:
            raise InvalidContestError("Question score must be greater than 0")

    @staticmethod
    def validate_question_duration(duration: int | None) -> None:
        """
        Validate that question duration is a positive integer.

        Args:
            duration: The time allocated for this question in seconds.

        Raises:
            InvalidContestError: If duration is not positive.
        """
        if duration is not None and duration <= 0:
            raise InvalidContestError("Question duration must be greater than 0")

    @staticmethod
    def validate_batch_add_limit(count: int, limit: int = 50) -> None:
        """
        Validate that the number of questions being added doesn't exceed the batch limit.

        Args:
            count: Number of questions in the batch request.
            limit: Maximum allowed questions per batch (default 50).

        Raises:
            InvalidContestError: If count exceeds the limit.
        """
        if count > limit:
            raise InvalidContestError(f"Cannot add more than {limit} questions at once")

    @staticmethod
    def validate_not_deleted(status: ContestStatus, contest_id: UUID) -> None:
        """
        Validate that the contest is not soft-deleted.

        Args:
            status: Status of the contest.
            contest_id: ID of the contest for error context.

        Raises:
            ContestNotFoundError: If the contest is marked as deleted.
        """
        if status == ContestStatus.DELETED:
            raise ContestNotFoundError(str(contest_id))

    @staticmethod
    def validate_contest_can_be_published(
        status: ContestStatus, contest_id: UUID
    ) -> None:
        """
        Validate that contest is in DRAFT status before publishing.

        Args:
            status: Current contest status
            contest_id: ID of the contest

        Raises:
            InvalidContestStateError: If contest is not in DRAFT status
        """
        if status != ContestStatus.DRAFT:
            raise InvalidContestStateError(
                str(contest_id), "publish", status, ContestStatus.DRAFT
            )

    @staticmethod
    def validate_contest_can_be_restored(
        status: ContestStatus, contest_id: UUID
    ) -> None:
        """
        Validate that contest is soft-deleted before restoring.

        Args:
            status: Status of the contest
            contest_id: ID of the contest

        Raises:
            InvalidContestStateError: If contest is not soft-deleted
        """
        if status != ContestStatus.DELETED:
            raise InvalidContestStateError(
                str(contest_id), "restore", "active", "soft-deleted"
            )

    @staticmethod
    def validate_questions_in_contest(
        request_q_ids: set[UUID], existing_q_ids: set[UUID], contest_id: UUID
    ) -> None:
        """
        Validate that all requested question IDs belong to the specified contest.

        Args:
            request_q_ids: Set of question IDs from the request.
            existing_q_ids: Set of question IDs currently in the contest.
            contest_id: ID of the contest for error context.

        Raises:
            QuestionNotInContestError: If any requested ID is missing from the contest.
        """
        if not request_q_ids.issubset(existing_q_ids):
            missing = request_q_ids - existing_q_ids
            raise QuestionNotInContestError(str(list(missing)[0]), str(contest_id))

    @staticmethod
    def validate_sequential_ordering(orders: list[int], total_count: int) -> None:
        """
        Validate that the provided orders form a sequential 1..N set.

        Args:
            orders: List of resulting orders after applying changes.
            total_count: Expected total number of questions.

        Raises:
            InvalidContestError: If orders are not sequential or contain duplicates.
        """
        new_orders = sorted(orders)
        expected_orders = list(range(1, total_count + 1))
        if new_orders != expected_orders:
            raise InvalidContestError(
                "Question orders must be sequential starting from 1 with no duplicates"
            )

    @staticmethod
    def validate_contest_is_published(status: ContestStatus, contest_id: UUID) -> None:
        """
        Validate that a contest is published.

        Args:
            status: Current status of the contest.
            contest_id: UUID of the contest.

        Raises:
            InvalidContestStateError: If the contest is not published.
        """
        if status != ContestStatus.PUBLISHED:
            raise InvalidContestStateError(
                str(contest_id), "start session for", status, ContestStatus.PUBLISHED
            )

    @staticmethod
    def validate_no_structural_changes_after_start(
        update_data: UpdateContestData,
        contest_id: UUID,
        has_sessions_started: bool,
    ) -> None:
        """
        Prevent edits to fields that define a contest's runtime/scoring model
        once any team/member has actually started a session.

        Fields like description, rules, image, max_teams, and extending
        end_time remain freely editable at any time; only the structural
        fields in STRUCTURAL_CONTEST_FIELDS are locked.

        Args:
            update_data: The patch data being applied (UNSET marks untouched fields).
            contest_id: ID of the contest, for error context.
            has_sessions_started: Whether any ContestTeamProgress row already
                exists for this contest.

        Raises:
            InvalidContestError: If a structural field is present in the patch
                and at least one session has already started.
        """
        if not has_sessions_started:
            return

        touched = [
            field
            for field in STRUCTURAL_CONTEST_FIELDS
            if getattr(update_data, field) is not UNSET
        ]
        if touched:
            raise InvalidContestError(
                f"Cannot change {', '.join(touched)} for contest {contest_id}: "
                "one or more participants have already started a session"
            )
