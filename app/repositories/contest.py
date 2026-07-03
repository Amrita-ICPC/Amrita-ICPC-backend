import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, asc, case, delete, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    ContestTeamProgress,
)
from app.models.question import Question, QuestionLanguage, Submission
from app.models.tag import QuestionTag, Tag
from app.models.user import User
from app.repositories.dto import (
    ContestFilters,
    ContestQuestionFilters,
    ContestQuestionsPaginatedResult,
    ContestsPaginatedResultWithStats,
    PaginationParams,
)
from app.repositories.dto.contest_question import AddContestQuestionData
from app.utils.enums import (
    ContestRunStatus,
    ContestStatus,
    ContestTeamMemberStatus,
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

    async def get_submissions_in_contest(
        self,
        contest_id: UUID,
        team_ids: list[UUID] | None = None,
        question_ids: list[UUID] | None = None,
        student_ids: list[UUID] | None = None,
    ) -> list[Submission]:
        """Retrieve submissions linked to a contest, optionally narrowed to
        specific teams, questions, and/or students (contest team members).

        Args:
            contest_id: Contest identifier.
            team_ids: Optional list of contest team ids to restrict to.
            question_ids: Optional list of question ids to restrict to.
            student_ids: Optional list of contest team member ids to restrict to.

        Returns:
            list[Submission]: List of submissions matching the filters.
        """
        query = (
            select(Submission)
            .join(ContestSubmission, ContestSubmission.submission_id == Submission.id)
            .where(ContestSubmission.contest_id == contest_id)
        )
        if team_ids:
            query = query.where(ContestSubmission.contest_team_id.in_(team_ids))
        if question_ids:
            query = query.where(Submission.question_id.in_(question_ids))
        if student_ids:
            query = query.where(
                ContestSubmission.contest_team_member_id.in_(student_ids)
            )

        result = await self.db.execute(query)
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
    ) -> ContestsPaginatedResultWithStats:
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
            ContestsPaginatedResultWithStats containing total count, stats, and list of Contest objects
        """
        # Subqueries for counts
        question_count_sub = (
            select(func.count(ContestQuestion.question_id))
            .where(ContestQuestion.contest_id == Contest.id)
            .scalar_subquery()
        )
        team_count_sub = (
            select(func.count(ContestTeam.id))
            .where(
                ContestTeam.contest_id == Contest.id,
                ContestTeam.team_status == TeamStatus.CONFIRMED,
                ContestTeam.approval_status == TeamApprovalStatus.APPROVED,
            )
            .scalar_subquery()
        )

        base_query = select(
            Contest,
            question_count_sub.label("question_count"),
            team_count_sub.label("team_count"),
        )

        # Apply permission filter
        base_query = self._apply_permission_filter(base_query, user_id, is_admin)

        # Filter out soft-deleted contests
        base_query = base_query.filter(Contest.status != ContestStatus.DELETED)

        # Apply search and status filters
        base_query = self._apply_search_and_status_filters(base_query, filters)

        # Apply visibility filter
        if filters.is_public is not None:
            base_query = base_query.filter(Contest.is_public == filters.is_public)

        # Get stats before temporal filters and pagination
        now = datetime.now(timezone.utc)
        stats_sub = base_query.with_only_columns(
            Contest.id,
            Contest.start_time,
            Contest.end_time,
        ).subquery()

        stats_query = select(
            func.count(stats_sub.c.id).label("total_count"),
            func.count(case((stats_sub.c.start_time > now, 1))).label("upcoming_count"),
            func.count(
                case(
                    (
                        and_(
                            stats_sub.c.start_time <= now,
                            or_(
                                stats_sub.c.end_time.is_(None),
                                stats_sub.c.end_time >= now,
                            ),
                        ),
                        1,
                    )
                )
            ).label("live_count"),
            func.count(
                case(
                    (
                        and_(
                            stats_sub.c.end_time.is_not(None),
                            stats_sub.c.end_time < now,
                        ),
                        1,
                    )
                )
            ).label("completed_count"),
        )

        stats_result = await self.db.execute(stats_query)
        stats_row = stats_result.fetchone()

        upcoming_count = 0
        live_count = 0
        completed_count = 0
        if stats_row:
            stats_row[0] or 0
            upcoming_count = stats_row[1] or 0
            live_count = stats_row[2] or 0
            completed_count = stats_row[3] or 0

        # Apply run_status filter using SQL datetime comparisons
        if filters.run_status is not None:
            if filters.run_status == ContestRunStatus.UPCOMING:
                base_query = base_query.filter(Contest.start_time > now)
            elif filters.run_status == ContestRunStatus.LIVE:
                base_query = base_query.filter(
                    Contest.start_time <= now,
                    or_(
                        Contest.end_time.is_(None),
                        Contest.end_time >= now,
                    ),
                )
            elif filters.run_status == ContestRunStatus.ENDED:
                base_query = base_query.filter(Contest.end_time < now)

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
        rows = result.unique().all()
        contests = []
        for row in rows:
            contest = row[0]
            contest.question_count = row[1] or 0
            contest.team_count = row[2] or 0
            contests.append(contest)

        return ContestsPaginatedResultWithStats(
            total=total,
            items=contests,
            live_count=live_count,
            upcoming_count=upcoming_count,
            completed_count=completed_count,
        )

    async def get_soft_deleted_contests(
        self,
        user_id: UUID,
        is_admin: bool,
        filters: ContestFilters,
        pagination: PaginationParams,
    ) -> ContestsPaginatedResultWithStats:
        """
        Retrieve soft-deleted contests with optional filtering and pagination.

        Uses same filtering logic as get_contests_with_filters but only returns soft-deleted contests.

        Args:
            user_id: ID of the user requesting contests
            is_admin: Whether the user has admin privileges
            filters: ContestFilters object containing optional search_term and status
            pagination: PaginationParams object containing skip and limit values

        Returns:
            ContestsPaginatedResultWithStats containing total count, stats, and list of soft-deleted Contest objects
        """
        # Subqueries for counts
        question_count_sub = (
            select(func.count(ContestQuestion.question_id))
            .where(ContestQuestion.contest_id == Contest.id)
            .scalar_subquery()
        )
        team_count_sub = (
            select(func.count(ContestTeam.id))
            .where(
                ContestTeam.contest_id == Contest.id,
                ContestTeam.team_status == TeamStatus.CONFIRMED,
                ContestTeam.approval_status == TeamApprovalStatus.APPROVED,
            )
            .scalar_subquery()
        )

        base_query = select(
            Contest,
            question_count_sub.label("question_count"),
            team_count_sub.label("team_count"),
        )

        # Apply permission filter
        base_query = self._apply_permission_filter(base_query, user_id, is_admin)

        # Filter for soft-deleted contests only
        base_query = base_query.filter(Contest.status == ContestStatus.DELETED)

        # Apply search and status filters
        base_query = self._apply_search_and_status_filters(base_query, filters)

        # Get distinct results
        base_query = base_query.distinct()

        # Get stats before pagination
        now = datetime.now(timezone.utc)
        stats_sub = base_query.with_only_columns(
            Contest.id,
            Contest.start_time,
            Contest.end_time,
        ).subquery()

        stats_query = select(
            func.count(stats_sub.c.id).label("total_count"),
            func.count(case((stats_sub.c.start_time > now, 1))).label("upcoming_count"),
            func.count(
                case(
                    (
                        and_(
                            stats_sub.c.start_time <= now,
                            or_(
                                stats_sub.c.end_time.is_(None),
                                stats_sub.c.end_time >= now,
                            ),
                        ),
                        1,
                    )
                )
            ).label("live_count"),
            func.count(
                case(
                    (
                        and_(
                            stats_sub.c.end_time.is_not(None),
                            stats_sub.c.end_time < now,
                        ),
                        1,
                    )
                )
            ).label("completed_count"),
        )

        stats_result = await self.db.execute(stats_query)
        stats_row = stats_result.fetchone()

        upcoming_count = 0
        live_count = 0
        completed_count = 0
        if stats_row:
            stats_row[0] or 0
            upcoming_count = stats_row[1] or 0
            live_count = stats_row[2] or 0
            completed_count = stats_row[3] or 0

        # Get total count before pagination
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Contest.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        rows = result.unique().all()
        contests = []
        for row in rows:
            contest = row[0]
            contest.question_count = row[1] or 0
            contest.team_count = row[2] or 0
            contests.append(contest)

        return ContestsPaginatedResultWithStats(
            total=total,
            items=contests,
            live_count=live_count,
            upcoming_count=upcoming_count,
            completed_count=completed_count,
        )

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

    async def get_contest_question(
        self, contest_id: UUID, question_id: UUID
    ) -> ContestQuestion | None:
        """
        Retrieve a specific contest question link.

        Args:
            contest_id: Contest ID
            question_id: Question ID

        Returns:
            ContestQuestion object if found, otherwise None
        """
        result = await self.db.execute(
            select(ContestQuestion).filter(
                ContestQuestion.contest_id == contest_id,
                ContestQuestion.question_id == question_id,
            )
        )
        return result.scalars().first()

    async def update_team_member_progress_scores(
        self, contest_id: UUID, member_scores: dict[UUID, int]
    ) -> None:
        """
        Update the scores for multiple team members in the contest.

        Args:
            contest_id: Contest ID
            member_scores: Dictionary mapping contest_team_member_id to total score
        """
        if not member_scores:
            return

        # Use CASE statement for bulk update
        score_cases = case(
            {member_id: score for member_id, score in member_scores.items()},
            value=ContestTeamProgress.contest_team_member_id,
        )

        stmt = (
            update(ContestTeamProgress)
            .where(
                and_(
                    ContestTeamProgress.contest_id == contest_id,
                    ContestTeamProgress.contest_team_member_id.in_(
                        member_scores.keys()
                    ),
                )
            )
            .values(score=score_cases)
        )

        await self.db.execute(stmt)
        await self.db.flush()

    async def ensure_team_member_progress_rows(
        self, contest_id: UUID, member_team_ids: dict[UUID, UUID]
    ) -> None:
        """
        Create missing progress rows for contest team members before score updates.

        Uses a single INSERT ... ON CONFLICT DO NOTHING so concurrent calls (e.g.
        two overlapping score-recompute requests) can't both observe a row as
        "missing" and race to insert it, which would otherwise raise an
        IntegrityError on the unique (contest_id, contest_team_id,
        contest_team_member_id) index.

        Args:
            contest_id: Contest ID
            member_team_ids: Mapping from contest_team_member_id to contest_team_id
        """
        if not member_team_ids:
            return

        stmt = (
            pg_insert(ContestTeamProgress)
            .values(
                [
                    {
                        "contest_id": contest_id,
                        "contest_team_id": team_id,
                        "contest_team_member_id": member_id,
                        "score": 0,
                    }
                    for member_id, team_id in member_team_ids.items()
                ]
            )
            .on_conflict_do_nothing(
                index_elements=[
                    "contest_id",
                    "contest_team_id",
                    "contest_team_member_id",
                ]
            )
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def recompute_member_score(
        self,
        contest_id: UUID,
        contest_team_id: UUID,
        contest_team_member_id: UUID,
    ) -> None:
        """
        Recompute and persist one contest team member's live score.

        Mirrors the scoring rule used by the contest-wide recompute
        (``update_team_member_progress_scores``): for each question, take the
        member's best score among their evaluated submissions, then sum those
        best-per-question scores. Unlike the contest-wide path, the aggregate
        is computed *inside* a single ``UPDATE ... SET score = (SELECT ...)``
        statement scoped to this one member, instead of a separate read step
        followed by a write. That means there is no read-compute-write window
        for two calls to race in: Postgres takes the row lock on this
        member's ``contest_team_progress`` row when the UPDATE starts, so a
        second concurrent call for the same member simply waits for the first
        to commit and then computes its aggregate against the now-current
        data - it can never overwrite a fresher result with a stale one.

        Intended to be called right after a submission is scored, so the
        leaderboard reflects every evaluation live instead of requiring a
        manual contest-wide recompute.

        Args:
            contest_id: Contest ID.
            contest_team_id: ContestTeam ID (not the underlying Team ID).
            contest_team_member_id: Contest team member ID who submitted.
        """
        # Guarantee the row exists (e.g. this member's first evaluated
        # submission) before updating it; upsert-safe under concurrency.
        await self.ensure_team_member_progress_rows(
            contest_id, {contest_team_member_id: contest_team_id}
        )

        best_per_question = (
            select(
                Submission.question_id,
                func.max(Submission.score).label("best_score"),
            )
            .select_from(ContestSubmission)
            .join(Submission, Submission.id == ContestSubmission.submission_id)
            .where(
                ContestSubmission.contest_id == contest_id,
                ContestSubmission.contest_team_member_id == contest_team_member_id,
                Submission.is_evaluated.is_(True),
            )
            .group_by(Submission.question_id)
            .subquery()
        )
        total_score = (
            select(func.coalesce(func.sum(best_per_question.c.best_score), 0))
            .select_from(best_per_question)
            .scalar_subquery()
        )

        await self.db.execute(
            update(ContestTeamProgress)
            .where(
                ContestTeamProgress.contest_id == contest_id,
                ContestTeamProgress.contest_team_member_id == contest_team_member_id,
            )
            .values(score=total_score)
        )
        await self.db.flush()

    async def acquire_contest_score_lock(self, contest_id: UUID) -> None:
        """
        Serialize concurrent score recomputations for a single contest.

        Takes a Postgres transaction-scoped advisory lock keyed by the contest
        id. If a recompute for the same contest is already in flight (e.g. an
        admin double-clicking "recompute scores", or a retried request racing
        the original), this blocks until it finishes instead of letting two
        full read-compute-write passes interleave and overwrite each other's
        result with stale data. The lock is released automatically when the
        current transaction commits or rolls back. Different contests use
        different lock keys and never block each other.

        Args:
            contest_id: Contest ID to serialize recomputation for.
        """
        await self.db.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(str(contest_id))))
        )

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
                max_submission=item.max_submission,
                bank_question_id=item.bank_question_id,
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

    async def get_teams_ranked_by_score(
        self,
        contest_id: UUID,
        search_term: str | None = None,
        sort_order: str = "desc",
        skip: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[tuple[ContestTeam, int]], int]:
        """Aggregate team scores from ContestTeamProgress and return teams sorted.

        Efficient query:
          JOIN ContestTeam → ContestTeamMember (ACCEPTED) → ContestTeamProgress,
          compute ROUND(AVG(score)) per team, ORDER BY total DESC.

        The AVG mirrors the leaderboard algorithm:
          team_total = mean of per-member total scores.

        Args:
            contest_id: ID of the contest.
            search_term: Optional term to filter teams by name.
            sort_order: 'asc' or 'desc' for score sorting.
            skip: Optional pagination offset.
            limit: Optional pagination limit.

        Returns:
            Tuple containing:
            - List of (ContestTeam, rounded_avg_score) tuples
            - Total count of matching teams
        """
        from app.models.contest import ContestTeamMember

        # 1. Get total count
        count_stmt = select(func.count(ContestTeam.id)).where(
            ContestTeam.contest_id == contest_id,
            ContestTeam.team_status == TeamStatus.CONFIRMED,
            ContestTeam.approval_status == TeamApprovalStatus.APPROVED,
        )
        if search_term:
            count_stmt = count_stmt.where(ContestTeam.name.ilike(f"%{search_term}%"))

        total_count = await self.db.scalar(count_stmt) or 0

        # 2. Get ranked teams
        avg_score = func.coalesce(
            func.round(func.avg(ContestTeamProgress.score)), 0
        ).label("team_score")

        stmt = (
            select(ContestTeam, avg_score)
            .options(selectinload(ContestTeam.contest_team_member))
            .outerjoin(
                ContestTeamMember,
                and_(
                    ContestTeamMember.contest_team_id == ContestTeam.id,
                    ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED,
                ),
            )
            .outerjoin(
                ContestTeamProgress,
                and_(
                    ContestTeamProgress.contest_team_id == ContestTeam.id,
                    ContestTeamProgress.contest_team_member_id == ContestTeamMember.id,
                    ContestTeamProgress.contest_id == contest_id,
                ),
            )
            .where(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_status == TeamStatus.CONFIRMED,
                ContestTeam.approval_status == TeamApprovalStatus.APPROVED,
            )
        )

        if search_term:
            stmt = stmt.where(ContestTeam.name.ilike(f"%{search_term}%"))

        stmt = stmt.group_by(ContestTeam.id)

        if sort_order == "asc":
            stmt = stmt.order_by(asc("team_score"), ContestTeam.name.asc())
        else:
            stmt = stmt.order_by(desc("team_score"), ContestTeam.name.asc())

        if skip is not None:
            stmt = stmt.offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return [(row[0], int(row[1])) for row in result.all()], total_count

    async def get_team_rank_and_score(
        self, contest_id: UUID, contest_team_id: UUID, sort_order: str = "desc"
    ) -> tuple[int, int] | None:
        """Compute a single team's rank/score within the contest standings.

        Uses a RANK() window function so the team's rank can be resolved
        without fetching/paginating the entire leaderboard.

        Args:
            contest_id: ID of the contest.
            contest_team_id: ID of the team to look up.
            sort_order: 'asc' or 'desc' for score sorting (must match the
                leaderboard's sort order for ranks to be consistent).

        Returns:
            Tuple of (rank, score), or None if the team is not part of the
            ranked standings (e.g. not CONFIRMED/APPROVED).
        """
        from app.models.contest import ContestTeamMember

        avg_score = func.coalesce(
            func.round(func.avg(ContestTeamProgress.score)), 0
        ).label("team_score")
        order_col = asc("team_score") if sort_order == "asc" else desc("team_score")

        ranked = (
            select(
                ContestTeam.id.label("team_id"),
                avg_score,
                func.rank().over(order_by=order_col).label("team_rank"),
            )
            .outerjoin(
                ContestTeamMember,
                and_(
                    ContestTeamMember.contest_team_id == ContestTeam.id,
                    ContestTeamMember.status == ContestTeamMemberStatus.ACCEPTED,
                ),
            )
            .outerjoin(
                ContestTeamProgress,
                and_(
                    ContestTeamProgress.contest_team_id == ContestTeam.id,
                    ContestTeamProgress.contest_team_member_id == ContestTeamMember.id,
                    ContestTeamProgress.contest_id == contest_id,
                ),
            )
            .where(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_status == TeamStatus.CONFIRMED,
                ContestTeam.approval_status == TeamApprovalStatus.APPROVED,
            )
            .group_by(ContestTeam.id)
            .subquery()
        )

        stmt = select(ranked.c.team_rank, ranked.c.team_score).where(
            ranked.c.team_id == contest_team_id
        )
        row = (await self.db.execute(stmt)).first()
        return (int(row.team_rank), int(row.team_score)) if row else None
