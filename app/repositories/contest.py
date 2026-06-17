import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, asc, case, delete, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.exceptions.contest import (
    ContestNotFoundError,
    DuplicateQuestionOrderError,
    InstructorNotAssignedError,
    QuestionAlreadyInContestError,
)
from app.exceptions.user import UserNotFoundError
from app.models import Audience
from app.models.audience import ContestAudience
from app.models.contest import (
    Contest,
    ContestInstructor,
    ContestQuestion,
    ContestSubmission,
    ContestTeam,
)
from app.models.question import Question, QuestionLanguage, Submission
from app.models.tag import QuestionTag, Tag
from app.models.user import User
from app.repositories.dto import (
    ContestFilters,
    ContestQuestionFilters,
    ContestQuestionsPaginatedResult,
    PaginatedResult,
    PaginationParams,
)
from app.repositories.dto.contest_question import AddContestQuestionData
from app.utils.enums import (
    ContestRunStatus,
    ContestStatus,
    QuestionDifficulty,
    TeamApprovalStatus,
    TeamStatus,
)


class ContestRepository:
    """Repository for contest-related database operations.

    This class implements the Repository Pattern, providing a clean abstraction
    over database operations for contest management. It encapsulates all SQL queries
    and ORM interactions, keeping the service layer database-agnostic.

    Responsibilities:
        - Execute all database queries for contests
        - Handle ORM relationships and eager loading optimizations
        - Provide type-safe data access methods
        - Raise domain-specific exceptions (not database exceptions)
        - Return domain objects and DTOs (not raw query results)

    Design Principles:
        - Single Responsibility: Only handles contest data access
        - Encapsulation: Hides SQLAlchemy implementation details
        - Fail Fast: Raises exceptions immediately on data not found
        - Type Safety: Uses DTOs for data transfer

    Key Methods:
        - Contest CRUD: create_contest, update_contest, delete_contest
        - Contest Queries: get_contest_or_raise, get_contests_with_filters
        - Soft Delete: soft_delete_contest, restore_contest, get_soft_deleted_contests
        - Publishing: publish_contest
        - Instructors: assign_instructor, remove_instructor, get_contest_instructors_paginated

    Exception Strategy:
        - Raises domain exceptions (ContestNotFoundError, etc.)
        - Never exposes SQLAlchemy exceptions to callers
        - Provides clear error messages with entity IDs
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _translate_contest_question_integrity_error(
        self,
        exc: IntegrityError,
        *,
        contest_id: UUID,
        question_id: UUID | None = None,
        order: int | None = None,
    ) -> None:
        """Translate contest_question unique violations to domain exceptions."""
        orig = getattr(exc, "orig", None)
        diag = getattr(orig, "diag", None)
        constraint_name = (
            getattr(diag, "constraint_name", None)
            or getattr(orig, "constraint_name", None)
            or ""
        )
        message = str(orig or exc)
        normalized_message = message.lower()
        normalized_constraint = constraint_name.lower()

        is_question_duplicate = (
            normalized_constraint == "contest_question_pkey"
            or (
                "contest_question" in normalized_constraint
                and "pkey" in normalized_constraint
            )
            or "contest_question_pkey" in normalized_message
            or "(contest_id, question_id)" in normalized_message
        )

        if is_question_duplicate:
            resolved_question_id = question_id
            if resolved_question_id is None:
                match = re.search(
                    r"\(contest_id,\s*question_id\)=\([^,]+,\s*([0-9a-f-]{36})\)",
                    normalized_message,
                )
                if match:
                    resolved_question_id = UUID(match.group(1))
            raise QuestionAlreadyInContestError(
                str(resolved_question_id or "unknown"),
                str(contest_id),
            ) from None

        is_order_duplicate = (
            normalized_constraint == "contest_question_contest_id_order_key"
            or (
                "contest_question" in normalized_constraint
                and "order" in normalized_constraint
            )
            or "contest_question_contest_id_order_key" in normalized_message
            or "(contest_id, order)" in normalized_message
            or '(contest_id, "order")' in normalized_message
        )

        if is_order_duplicate:
            resolved_order = order
            if resolved_order is None:
                match = re.search(
                    r"\(contest_id,\s*\"?order\"?\)=\([^,]+,\s*([0-9]+)\)",
                    normalized_message,
                )
                if match:
                    resolved_order = int(match.group(1))
            raise DuplicateQuestionOrderError(
                resolved_order if resolved_order is not None else -1,
                str(contest_id),
            ) from None

    async def get_contest_or_raise(self, contest_id: UUID) -> Contest:
        """
        Retrieve a contest by its ID or raise an exception if not found.

        Args:
            contest_id: ID of the contest to retrieve.
        Returns:
            The Contest object if found.
        Raises:
            ContestNotFoundError: If the contest with the given ID does not exist.
        """
        result = await self.db.execute(
            select(Contest)
            .filter(Contest.id == contest_id)
            .options(
                selectinload(Contest.audience_links).selectinload(
                    ContestAudience.audience
                )
            )
        )
        contest = result.scalars().first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))
        return contest

    async def count_questions_in_contest(self, contest_id: UUID) -> int:
        """Count the number of questions in a contest.

        Args:
            contest_id: Contest identifier.

        Returns:
            Total number of questions linked to the contest.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(ContestQuestion)
            .filter(ContestQuestion.contest_id == contest_id)
        )
        return int(result.scalar() or 0)

    async def count_submissions_in_contest(self, contest_id: UUID) -> int:
        """Count the number of submissions for questions in a contest.

        Notes:
            The Submission model does not store contest_id directly. This count is
            computed by joining submissions to questions that are linked to the
            contest via `contest_question`.

        Args:
            contest_id: Contest identifier.

        Returns:
            Total number of submissions for the contest's questions.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(Submission)
            .join(
                ContestQuestion,
                ContestQuestion.question_id == Submission.question_id,
            )
            .filter(ContestQuestion.contest_id == contest_id)
        )
        return int(result.scalar() or 0)

    async def get_submissions_in_contest(self, contest_id: UUID) -> list[Submission]:
        """Retrieve all submissions linked to a contest.

        Args:
            contest_id: Contest identifier.

        Returns:
            list[Submission]: List of submissions for the contest.
        """
        result = await self.db.execute(
            select(Submission)
            .join(ContestSubmission, ContestSubmission.submission_id == Submission.id)
            .where(ContestSubmission.contest_id == contest_id)
        )
        return list(result.scalars().all())

    # TODO: Update the filters with factory and builder design pattern

    def _apply_permission_filter(self, query, user_id: UUID, is_admin: bool):
        """
        Apply permission-based filtering: admins see all, non-admins see only their own or assigned.

        Consolidates permission logic used by both get_contests_with_filters and get_soft_deleted_contests.

        Args:
            query: SQLAlchemy select query
            user_id: User requesting the contests
            is_admin: Whether user is admin

        Returns:
            Filtered query
        """
        if not is_admin:
            instructor_exists = (
                select(1)
                .select_from(ContestInstructor)
                .where(
                    ContestInstructor.contest_id == Contest.id,
                    ContestInstructor.instructor_id == user_id,
                )
                .exists()
            )
            query = query.filter(
                or_(
                    Contest.created_by == user_id,
                    instructor_exists,
                )
            )
        return query

    def _apply_search_and_status_filters(self, query, filters: ContestFilters):
        """
        Apply search term and status filters.

        Consolidates filter logic used by both get_contests_with_filters and get_soft_deleted_contests.

        Args:
            query: SQLAlchemy select query
            filters: ContestFilters with optional search_term and status

        Returns:
            Filtered query
        """
        if filters.search_term:
            query = query.filter(Contest.name.ilike(f"%{filters.search_term}%"))

        if filters.status:
            query = query.filter(Contest.status == filters.status)

        return query

    async def get_contests_with_filters(
        self,
        user_id: UUID,
        is_admin: bool,
        filters: ContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve contests with optional filtering and pagination.

        This method builds a query based on user permissions (admin vs non-admin),
        applies filters for search, status, and visibility, and returns paginated results.

        Args:
            user_id: ID of the user requesting contests
            is_admin: Whether the user has admin privileges
            filters: ContestFilters object containing optional search_term, status, and is_public
            pagination: PaginationParams object containing skip and limit values

        Returns:
            PaginatedResult containing total count and list of Contest objects
        """
        base_query = select(Contest)

        # Apply permission filter
        base_query = self._apply_permission_filter(base_query, user_id, is_admin)

        # Filter out soft-deleted contests
        base_query = base_query.filter(Contest.status != ContestStatus.DELETED)

        # Apply search and status filters
        base_query = self._apply_search_and_status_filters(base_query, filters)

        # Apply run_status filter using SQL datetime comparisons
        now = datetime.now(timezone.utc)
        if filters.run_status is not None:
            if filters.run_status == ContestRunStatus.UPCOMING:
                base_query = base_query.filter(Contest.start_time > now)
            elif filters.run_status == ContestRunStatus.LIVE:
                base_query = base_query.filter(
                    Contest.start_time <= now, Contest.end_time >= now
                )
            elif filters.run_status == ContestRunStatus.ENDED:
                base_query = base_query.filter(Contest.end_time < now)

        # Apply visibility filter
        if filters.is_public is not None:
            base_query = base_query.filter(Contest.is_public == filters.is_public)

        # Eager load audiences
        base_query = base_query.options(
            selectinload(Contest.audience_links).joinedload(ContestAudience.audience)
        )

        # Get total count before pagination
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Contest.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Default sort: LIVE → UPCOMING → ENDED (then by start_time ascending)
        run_status_order = case(
            (Contest.start_time <= now, case((Contest.end_time >= now, 0), else_=2)),
            else_=1,
        )
        base_query = base_query.order_by(run_status_order, Contest.start_time.asc())

        # Apply pagination
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        contests = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=contests)

    async def get_soft_deleted_contests(
        self,
        user_id: UUID,
        is_admin: bool,
        filters: ContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve soft-deleted contests with optional filtering and pagination.

        Uses same filtering logic as get_contests_with_filters but only returns soft-deleted contests.

        Args:
            user_id: ID of the user requesting contests
            is_admin: Whether the user has admin privileges
            filters: ContestFilters object containing optional search_term and status
            pagination: PaginationParams object containing skip and limit values

        Returns:
            PaginatedResult containing total count and list of soft-deleted Contest objects
        """
        base_query = select(Contest)

        # Apply permission filter
        base_query = self._apply_permission_filter(base_query, user_id, is_admin)

        # Filter for soft-deleted contests only
        base_query = base_query.filter(Contest.status == ContestStatus.DELETED)

        # Apply search and status filters
        base_query = self._apply_search_and_status_filters(base_query, filters)

        # Get distinct results
        base_query = base_query.distinct()

        # Get total count before pagination
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Contest.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        contests = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=contests)

    async def create_contest(self, contest: Contest) -> Contest:
        """
        Create a new contest in the database.

        Args:
            contest: Contest ORM object

        Returns:
            The created Contest object with ID and timestamps populated
        """
        self.db.add(contest)
        await self.db.flush()
        await self.db.refresh(contest)
        return contest

    async def link_audiences_to_contest(
        self, contest_id: UUID, audience_ids: list[UUID]
    ) -> None:
        """
        Link audiences to a contest.

        Only adds links for audience IDs that are not already associated
        with the contest to avoid duplicate key errors.

        Args:
            contest_id: ID of the contest
            audience_ids: List of audience IDs to link
        """
        if not audience_ids:
            return

        # Identify existing links to ensure idempotency
        existing_links = await self.get_contest_audience_ids(contest_id)
        new_ids = list(
            dict.fromkeys(aid for aid in audience_ids if aid not in existing_links)
        )

        if not new_ids:
            return

        links = [
            ContestAudience(contest_id=contest_id, audience_id=audience_id)
            for audience_id in new_ids
        ]
        self.db.add_all(links)
        await self.db.flush()

    async def unlink_audiences_from_contest(
        self, contest_id: UUID, audience_ids: list[UUID]
    ) -> None:
        """
        Remove audience links from a contest.

        Args:
            contest_id: ID of the contest
            audience_ids: List of audience IDs to remove
        """
        if not audience_ids:
            return

        await self.db.execute(
            delete(ContestAudience).where(
                ContestAudience.contest_id == contest_id,
                ContestAudience.audience_id.in_(audience_ids),
            )
        )
        await self.db.flush()

    async def get_contest_audience_ids(self, contest_id: UUID) -> set[UUID]:
        """
        Fetch all audience IDs currently linked to a contest.

        Args:
            contest_id: ID of the contest

        Returns:
            Set of associated audience IDs
        """
        result = await self.db.execute(
            select(ContestAudience.audience_id)
            .join(Contest, Contest.id == ContestAudience.contest_id)
            .where(
                ContestAudience.contest_id == contest_id,
                Contest.status != ContestStatus.DELETED,
            )
        )
        return set(result.scalars().all())

    async def get_contest_audiences_with_details(
        self, contest_id: UUID
    ) -> list[Audience]:
        """
        Fetch all audiences currently linked to a contest with full details.
        Only returns details if the contest is not deleted.

        Args:
            contest_id: ID of the contest

        Returns:
            List of associated Audience objects
        """
        from app.models.audience import Audience, ContestAudience

        result = await self.db.execute(
            select(Audience)
            .join(ContestAudience)
            .join(Contest, Contest.id == ContestAudience.contest_id)
            .where(
                ContestAudience.contest_id == contest_id,
                Contest.status != ContestStatus.DELETED,
            )
        )
        return list(result.scalars().all())

    async def update_contest(self, contest: Contest, user_id: UUID) -> Contest:
        """
        Update an existing contest in the database.

        Args:
            contest: Contest object to update (must have valid ID)
            update_data: UpdateContestData object with fields to update
            user_id: ID of the user performing the update

        Returns:
            The updated Contest object
        """
        contest.updated_by = user_id
        await self.db.flush()
        await self.db.refresh(contest)
        return contest

    async def delete_contest(self, contest: Contest) -> None:
        """
        Hard delete a contest from the database.

        Args:
            contest: Contest object to delete
        """
        await self.db.delete(contest)
        await self.db.flush()

    async def soft_delete_contest(self, contest: Contest, user_id: UUID) -> None:
        """
        Soft delete a contest by setting deletion flags.

        Args:
            contest: Contest object to soft delete
            user_id: ID of the user performing the soft delete
        """
        contest.status = ContestStatus.DELETED
        contest.deleted_at = datetime.now(timezone.utc)
        contest.deleted_by = user_id
        await self.db.flush()

    async def restore_contest(self, contest: Contest) -> Contest:
        """
        Restore a soft-deleted contest.

        Args:
            contest: Contest object to restore

        Returns:
            The restored Contest object
        """
        contest.status = ContestStatus.DRAFT
        contest.deleted_at = None
        contest.deleted_by = None
        await self.db.flush()
        await self.db.refresh(contest)
        return contest

    async def publish_contest(self, contest: Contest, user_id: UUID) -> None:
        """
        Publish a contest by setting published timestamp and updating status.

        Args:
            contest: Contest object to publish
            user_id: ID of the user publishing the contest
        """
        now = datetime.now(timezone.utc)
        contest.published_at = now
        contest.published_by = user_id
        contest.status = ContestStatus.PUBLISHED

        await self.db.flush()

    async def get_all_instructors_for_contest(self, contest_id: UUID) -> list[User]:
        """
        Retrieve all instructors assigned to a contest.

        Args:
            contest_id: ID of the contest

        Returns:
            List of User objects representing the instructors assigned to the contest
        """
        result = await self.db.execute(
            select(User)
            .join(ContestInstructor, User.id == ContestInstructor.instructor_id)
            .filter(ContestInstructor.contest_id == contest_id)
        )
        instructors = list(result.scalars().all())
        return instructors

    async def get_contest_instructors_paginated(
        self, contest_id: UUID, skip: int, limit: int
    ) -> tuple[int, list[User]]:
        """
        Retrieve instructors assigned to a contest with pagination.

        Args:
            contest_id: ID of the contest
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (total count, list of User objects)
        """
        base_query = (
            select(User)
            .join(ContestInstructor, User.id == ContestInstructor.instructor_id)
            .filter(ContestInstructor.contest_id == contest_id)
        )

        count_query = select(func.count()).select_from(
            base_query.with_only_columns(User.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0
        result = await self.db.execute(base_query.offset(skip).limit(limit))
        instructors: list[User] = list(result.unique().scalars().all())

        return total, instructors

    async def assign_instructor(
        self, contest_id: UUID, instructor_ids: list[UUID]
    ) -> None:
        """
        Assign instructors to a contest.

        Args:
            contest_id: ID of the contest
            instructor_ids: List of instructor IDs to assign
        """
        result = await self.db.execute(
            select(ContestInstructor).filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id.in_(instructor_ids),
            )
        )
        existing_assignments = list(result.scalars().all())
        existing_instructor_ids = {
            assignment.instructor_id for assignment in existing_assignments
        }
        new_instructor_ids = [
            iid for iid in instructor_ids if iid not in existing_instructor_ids
        ]
        instructors = [
            ContestInstructor(contest_id=contest_id, instructor_id=instructor_id)
            for instructor_id in new_instructor_ids
        ]
        if instructors:
            self.db.add_all(instructors)
            await self.db.flush()

    async def remove_instructor(
        self, contest_id: UUID, instructor_ids: list[UUID]
    ) -> None:
        """
        Remove instructors from a contest.

        Args:
            contest_id: ID of the contest
            instructor_ids: List of instructor IDs to remove
        """
        result = await self.db.execute(
            select(ContestInstructor).filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id.in_(instructor_ids),
            )
        )
        assignments = list(result.scalars().all())

        # Check if all instructors were found
        found_instructor_ids = {assignment.instructor_id for assignment in assignments}
        missing_instructor_ids = set(instructor_ids) - found_instructor_ids

        if missing_instructor_ids:
            # Raise exception for the first missing instructor ID
            missing_id = next(iter(missing_instructor_ids))
            raise InstructorNotAssignedError(str(missing_id), str(contest_id))

        # Delete all assignments
        for assignment in assignments:
            await self.db.delete(assignment)

        await self.db.flush()

    async def is_instructor_assigned(
        self, contest_id: UUID, instructor_id: UUID
    ) -> bool:
        """
        Check if an instructor is assigned to a contest.

        Args:
            contest_id: ID of the contest
            instructor_id: ID of the instructor

        Returns:
            True if the instructor is assigned, False otherwise
        """
        result = await self.db.execute(
            select(ContestInstructor).filter(
                ContestInstructor.contest_id == contest_id,
                ContestInstructor.instructor_id == instructor_id,
            )
        )
        assignment = result.scalars().first()
        return assignment is not None

    async def get_creator(self, user_id: UUID) -> User:
        result = await self.db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError(str(user_id))
        return user

    async def get_contest_questions_paginated(
        self,
        contest_id: UUID,
        pagination: PaginationParams,
        filters: ContestQuestionFilters,
    ) -> ContestQuestionsPaginatedResult:
        """
        Retrieve paginated questions for a contest with optional filtering.

        Filters questions by search term, difficulty, language, and tags.

        Args:
            contest_id: Contest ID
            pagination: Pagination parameters (skip, limit)
            filters: ContestQuestionFilters with optional search_term, difficulty, language_id, tag_id

        Returns:
            PaginatedResult with Question objects
        """
        # Build base query
        base_query = (
            select(Question)
            .join(ContestQuestion, ContestQuestion.question_id == Question.id)
            .filter(ContestQuestion.contest_id == contest_id)
            .options(
                selectinload(Question.languages).joinedload(QuestionLanguage.language),
                selectinload(Question.tags).joinedload(QuestionTag.tag),
                selectinload(Question.testcases),
            )
        )

        # Apply filters
        filter_conditions: list[ColumnElement[bool]] = []

        # Search term filter
        if filters.search_term:
            filter_conditions.append(
                Question.question_text.ilike(f"%{filters.search_term}%")
            )

        # Difficulty filter
        if filters.difficulty:
            filter_conditions.append(Question.difficulty == filters.difficulty)

        # Language filter
        if filters.language_id:
            base_query = base_query.join(
                QuestionLanguage, QuestionLanguage.question_id == Question.id
            )
            filter_conditions.append(
                QuestionLanguage.language_id == filters.language_id
            )

        # Tag filters
        if filters.tag_id or filters.tag_name:
            base_query = base_query.join(
                QuestionTag, QuestionTag.question_id == Question.id
            ).join(Tag, Tag.id == QuestionTag.tag_id)

            if filters.tag_id:
                filter_conditions.append(QuestionTag.tag_id == filters.tag_id)
            if filters.tag_name:
                filter_conditions.append(Tag.name.ilike(f"%{filters.tag_name}%"))

        # Combine with AND
        if filter_conditions:
            base_query = base_query.where(and_(*filter_conditions))

        # Apply sorting
        order_func = desc if filters.sort_order == "desc" else asc

        if filters.sort_by == "difficulty":
            difficulty_order = case(
                {
                    QuestionDifficulty.EASY: 1,
                    QuestionDifficulty.MEDIUM: 2,
                    QuestionDifficulty.HARD: 3,
                },
                value=Question.difficulty,
            )
            base_query = base_query.order_by(order_func(difficulty_order))
        else:
            # Default order by contest_question.order
            base_query = base_query.order_by(order_func(ContestQuestion.order))

        # Get total count
        count_query = (
            select(func.count(Question.id))
            .join(ContestQuestion, ContestQuestion.question_id == Question.id)
            .filter(ContestQuestion.contest_id == contest_id)
        )
        if filters.language_id:
            count_query = count_query.join(
                QuestionLanguage, QuestionLanguage.question_id == Question.id
            )
        if filters.tag_id or filters.tag_name:
            count_query = count_query.join(
                QuestionTag, QuestionTag.question_id == Question.id
            ).join(Tag, Tag.id == QuestionTag.tag_id)

        if filter_conditions:
            count_query = count_query.where(and_(*filter_conditions))

        total = (await self.db.execute(count_query)).scalar() or 0

        # Get difficulty counts for this contest
        difficulty_query = (
            select(
                Question.difficulty,
                func.count(Question.id).label("count"),
            )
            .join(ContestQuestion, ContestQuestion.question_id == Question.id)
            .where(ContestQuestion.contest_id == contest_id)
            .group_by(Question.difficulty)
        )
        difficulty_result = await self.db.execute(difficulty_query)
        counts = {row[0]: row[1] for row in difficulty_result.all()}

        # Apply pagination
        query = base_query.offset(pagination.skip).limit(pagination.limit)

        # Execute query
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return ContestQuestionsPaginatedResult(
            total=total,
            items=items,
            easy_count=counts.get(QuestionDifficulty.EASY, 0),
            medium_count=counts.get(QuestionDifficulty.MEDIUM, 0),
            hard_count=counts.get(QuestionDifficulty.HARD, 0),
        )

    async def get_ordered_question_orders_for_contest(
        self, contest_id: UUID
    ) -> list[ContestQuestion]:
        """
        Retrieve all question orders for a contest.

        Returns ContestQuestion objects that track the order assignment for questions.

        Args:
            contest_id: Contest ID

        Returns:
            List of ContestQuestion objects ordered by their order field
        """
        result = await self.db.execute(
            select(ContestQuestion)
            .filter(ContestQuestion.contest_id == contest_id)
            .order_by(ContestQuestion.order.asc())
        )
        return list(result.scalars().all())

    async def get_max_question_order(self, contest_id: UUID) -> int:
        """
        Get the maximum order of questions in a contest.

        Args:
            contest_id: Contest ID

        Returns:
            int: Maximum order value, or 0 if no questions exist.
        """
        result = await self.db.execute(
            select(func.max(ContestQuestion.order)).filter(
                ContestQuestion.contest_id == contest_id
            )
        )
        return result.scalar() or 0

    async def is_question_in_contest(self, contest_id: UUID, question_id: UUID) -> bool:
        """
        Check if a question exists in a contest.

        Args:
            contest_id: Contest ID
            question_id: Question ID

        Returns:
            True if question is in contest, False otherwise
        """
        result = await self.db.execute(
            select(ContestQuestion).filter(
                ContestQuestion.contest_id == contest_id,
                ContestQuestion.question_id == question_id,
            )
        )
        return result.scalars().first() is not None

    async def add_questions_to_contest(
        self,
        questions: list[AddContestQuestionData],
    ) -> list[ContestQuestion]:
        """Batch add questions to a contest.

        Args:
            questions: List of repository DTOs describing the contest-question linkage.

        Returns:
            List of created ContestQuestion ORM objects.

        Raises:
            DuplicateQuestionOrderError: If an order value violates uniqueness.
            QuestionAlreadyInContestError: If a question is already linked.
        """
        if not questions:
            return []

        entities = [
            ContestQuestion(
                contest_id=item.contest_id,
                question_id=item.question_id,
                order=item.order,
                duration=item.duration,
                score=item.score,
                created_by=item.created_by,
            )
            for item in questions
        ]

        try:
            self.db.add_all(entities)
            await self.db.flush()
        except IntegrityError as exc:
            first = questions[0]
            self._translate_contest_question_integrity_error(
                exc,
                contest_id=first.contest_id,
                question_id=first.question_id,
                order=first.order,
            )
            raise

        return entities

    async def remove_questions_from_contest(
        self,
        contest_id: UUID,
        question_ids: list[UUID],
    ) -> None:
        """Remove multiple questions from a contest.

        Args:
            contest_id: Contest ID.
            question_ids: Question IDs to remove.
        """
        if not question_ids:
            return

        await self.db.execute(
            delete(ContestQuestion).filter(
                ContestQuestion.contest_id == contest_id,
                ContestQuestion.question_id.in_(question_ids),
            )
        )
        await self.db.flush()

    async def reorder_questions_in_contest(
        self,
        contest_id: UUID,
        reorders: list[tuple[UUID, int]],
    ) -> None:
        """
        Bulk update the order of multiple questions in a contest using CASE for efficiency.
        Uses a two-step update to avoid temporary unique constraint violations.

        Args:
            contest_id: ID of the contest.
            reorders: List of (question_id, new_order) tuples.
        """
        if not reorders:
            return

        question_ids = [question_id for question_id, _ in reorders]

        max_order = await self.get_max_question_order(contest_id)
        # Step 1: Temporarily set orders to high values to avoid unique constraint issues
        temp_order_case = case(
            {
                question_id: max_order + i + 1
                for i, (question_id, _) in enumerate(reorders)
            },
            value=ContestQuestion.question_id,
        )

        await self.db.execute(
            update(ContestQuestion)
            .where(
                and_(
                    ContestQuestion.contest_id == contest_id,
                    ContestQuestion.question_id.in_(question_ids),
                )
            )
            .values(order=temp_order_case)
        )
        await self.db.flush()

        # Step 2: Apply final orders
        order_case = case(
            {question_id: order for question_id, order in reorders},
            value=ContestQuestion.question_id,
        )

        stmt = (
            update(ContestQuestion)
            .where(
                and_(
                    ContestQuestion.contest_id == contest_id,
                    ContestQuestion.question_id.in_(question_ids),
                )
            )
            .values(order=order_case)
        )

        await self.db.execute(stmt)
        await self.db.flush()

    async def get_contest_problems(
        self,
        contest_id: UUID,
    ) -> list[ContestQuestion]:
        """
        Retrieve all problems in a contest ordered by problem order.

        Args:
            contest_id: Contest ID

        Returns:
            List of ContestQuestion objects with eager-loaded relationships
        """
        result = await self.db.execute(
            select(ContestQuestion)
            .filter(ContestQuestion.contest_id == contest_id)
            .options(joinedload(ContestQuestion.question))
            .order_by(ContestQuestion.order.asc())
        )
        return list(result.unique().scalars().all())

    async def get_contest_leaderboard_raw_data(
        self, contest_id: UUID
    ) -> tuple[list[ContestTeam], list[Question], list[Submission]]:
        """
        Retrieve all raw data needed to calculate the contest leaderboard:
        - Confirmed and approved teams with their accepted members.
        - Questions assigned to the contest ordered by their position.
        - Submissions made under the contest, eager loading testcases and contest submission details.

        Args:
            contest_id: ID of the contest.

        Returns:
            tuple: (teams, questions, submissions)
        """
        # 1. Fetch confirmed/approved teams and their accepted members
        teams_result = await self.db.execute(
            select(ContestTeam)
            .options(selectinload(ContestTeam.contest_team_member))
            .where(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_status == TeamStatus.CONFIRMED,
                ContestTeam.approval_status == TeamApprovalStatus.APPROVED,
            )
        )
        teams = list(teams_result.scalars().all())

        # 2. Fetch all questions in the contest
        questions_result = await self.db.execute(
            select(Question)
            .join(ContestQuestion, ContestQuestion.question_id == Question.id)
            .where(ContestQuestion.contest_id == contest_id)
            .order_by(ContestQuestion.order.asc())
        )
        questions = list(questions_result.scalars().all())

        # 3. Fetch all submissions in the contest
        submissions_result = await self.db.execute(
            select(Submission)
            .options(
                selectinload(Submission.testcases),
                joinedload(Submission.contest_submission),
            )
            .join(ContestSubmission, ContestSubmission.submission_id == Submission.id)
            .where(ContestSubmission.contest_id == contest_id)
        )
        submissions = list(submissions_result.scalars().all())

        return teams, questions, submissions
