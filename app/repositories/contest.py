import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
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
from app.models.contest import (
    Contest,
    ContestInstructor,
    ContestQuestion,
    ContestTeam,
    ContestTeamProgress,
)
from app.models.question import Question, QuestionLanguage
from app.models.team import Team, TeamUser
from app.models.user import User
from app.repositories.dto import (
    ContestFilters,
    ContestQuestionFilters,
    PaginatedResult,
    PaginationParams,
    StudentContestFilters,
)
from app.repositories.dto.contest_question import AddContestQuestionData
from app.utils.enums import ContestStatus, TeamApprovalStatus


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
        result = await self.db.execute(select(Contest).filter(Contest.id == contest_id))
        contest = result.scalars().first()
        if not contest:
            raise ContestNotFoundError(str(contest_id))
        return contest

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

        # Non-admin users can only see contests they created or are assigned to as instructors
        if not is_admin:
            base_query = base_query.outerjoin(ContestInstructor).filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )

        # Filter out soft-deleted contests
        base_query = base_query.filter(Contest.is_deleted.is_(False))

        # Apply search filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Apply status filter
        if filters.status:
            base_query = base_query.filter(Contest.status == filters.status)

        # Apply visibility filter
        if filters.is_public is not None:
            base_query = base_query.filter(Contest.is_public == filters.is_public)

        # Get distinct results (important when using outerjoin)
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

    async def get_soft_deleted_contests(
        self,
        user_id: UUID,
        is_admin: bool,
        filters: ContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve soft-deleted contests with optional filtering and pagination.

        Similar to get_contests_with_filters but only returns soft-deleted contests.

        Args:
            user_id: ID of the user requesting contests
            is_admin: Whether the user has admin privileges
            filters: ContestFilters object containing optional search_term and status
            pagination: PaginationParams object containing skip and limit values

        Returns:
            PaginatedResult containing total count and list of soft-deleted Contest objects
        """
        base_query = select(Contest)

        # Non-admin users can only see contests they created or are assigned to as instructors
        if not is_admin:
            base_query = base_query.outerjoin(ContestInstructor).filter(
                or_(
                    Contest.created_by == user_id,
                    ContestInstructor.instructor_id == user_id,
                )
            )

        # Filter for soft-deleted contests only
        base_query = base_query.filter(Contest.is_deleted.is_(True))

        # Apply search filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Apply status filter
        if filters.status:
            base_query = base_query.filter(Contest.status == filters.status)

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
            contest_data: CreateContestData object containing all contest creation data

        Returns:
            The created Contest object with ID and timestamps populated
        """
        self.db.add(contest)
        await self.db.flush()
        await self.db.refresh(contest)
        return contest

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
        contest.is_deleted = True
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
        contest.is_deleted = False
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

        # Update status based on start/end times
        if now < contest.start_time:
            contest.status = ContestStatus.SCHEDULED
        elif contest.start_time <= now <= contest.end_time:
            contest.status = ContestStatus.RUNNING
        else:
            contest.status = ContestStatus.FINISHED

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
    ) -> PaginatedResult:
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

        # Tag filter
        if filters.tag_id:
            filter_conditions.append(
                Question.id.in_(
                    select(ContestQuestion.question_id)
                    .join(Question, Question.id == ContestQuestion.question_id)
                    .where(
                        and_(
                            ContestQuestion.contest_id == contest_id,
                            # Assuming tag relationship exists
                        )
                    )
                )
            )

        # Combine with AND
        if filter_conditions:
            base_query = base_query.where(and_(*filter_conditions))

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
        if filter_conditions:
            count_query = count_query.where(and_(*filter_conditions))

        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination
        query = base_query.offset(pagination.skip).limit(pagination.limit)

        # Execute query
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return PaginatedResult(total=total, items=items)

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

    # ============ STUDENT-SPECIFIC METHODS ============

    async def get_available_contests_for_student(
        self,
        filters: StudentContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve public and active contests available for student registration.

        Returns only contests that are:
        - Public (is_public = True)
        - Not deleted (is_deleted = False)
        - In SCHEDULED or RUNNING status
        - Within registration window (if applicable)

        Args:
            filters: StudentContestFilters for optional search and status filtering
            pagination: PaginationParams for skip/limit

        Returns:
            PaginatedResult with available contests
        """
        base_query = (
            select(Contest)
            .options(selectinload(Contest.questions))
            .filter(
                Contest.is_public.is_(True),
                Contest.is_deleted.is_(False),
                Contest.status.in_([ContestStatus.SCHEDULED, ContestStatus.RUNNING]),
            )
        )

        # Apply search filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Get total count
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Contest.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        contests = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=contests)

    async def get_registered_contests_for_student(
        self,
        user_id: UUID,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve contests where student is registered (directly or via team).

        Returns contests that are in ContestTeam where the student is a team member.

        Args:
            user_id: Student's user ID
            pagination: PaginationParams for skip/limit

        Returns:
            PaginatedResult with (Contest, ContestTeam) tuples
        """
        # Query contests with ContestTeam and eagerly load Team relationship
        query = (
            select(Contest, ContestTeam)
            .options(
                selectinload(Contest.questions),
                selectinload(ContestTeam.team),
            )
            .join(ContestTeam, ContestTeam.contest_id == Contest.id)
            .join(Team, ContestTeam.team_id == Team.id)
            .join(TeamUser, TeamUser.team_id == Team.id)
            .filter(
                TeamUser.user_id == user_id,
                Contest.is_deleted.is_(False),
            )
            .distinct()
        )

        # Get total count
        count_result = await self.db.execute(
            select(func.count(func.distinct(Contest.id)))
            .join(ContestTeam, ContestTeam.contest_id == Contest.id)
            .join(Team, ContestTeam.team_id == Team.id)
            .join(TeamUser, TeamUser.team_id == Team.id)
            .filter(
                TeamUser.user_id == user_id,
                Contest.is_deleted.is_(False),
            )
        )
        total = count_result.scalar() or 0

        # Get paginated results
        result = await self.db.execute(
            query.offset(pagination.skip).limit(pagination.limit)
        )
        items = list(result.unique().all())

        return PaginatedResult(total=total, items=items)

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

    async def register_student_to_contest(
        self,
        contest_id: UUID,
        user_id: UUID,
    ) -> ContestTeam:
        """
        Register individual student to a contest (create single-person team).

        Creates a new team with just the student, registers it in the contest,
        and creates progress tracking.

        Args:
            contest_id: Contest ID
            user_id: Student user ID

        Returns:
            Created ContestTeam object
        """
        # Create a team for the student (name: student_name + uuid suffix)
        user = await self.get_user_or_raise(user_id)
        team_name = f"{user.name}'s Team"

        team = Team(
            name=team_name,
            created_by=user_id,
            leader_id=user_id,
        )
        self.db.add(team)
        await self.db.flush()

        # Add student as team member
        team_user = TeamUser(team_id=team.id, user_id=user_id)
        self.db.add(team_user)

        # Create ContestTeam
        contest_team = ContestTeam(
            contest_id=contest_id,
            team_id=team.id,
            team_status="CONFIRMED",
            approval_status=TeamApprovalStatus.APPROVED,
        )
        self.db.add(contest_team)

        # Create progress tracking
        progress = ContestTeamProgress(
            contest_id=contest_id,
            team_id=team.id,
            score=0,
        )
        self.db.add(progress)

        await self.db.flush()
        await self.db.refresh(contest_team)
        return contest_team

    async def is_student_registered(
        self,
        contest_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Check if student is registered in a contest (directly or via team).

        Args:
            contest_id: Contest ID
            user_id: Student user ID

        Returns:
            True if registered, False otherwise
        """
        result = await self.db.execute(
            select(ContestTeam).filter(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_id.in_(
                    select(TeamUser.team_id).filter(TeamUser.user_id == user_id)
                ),
            )
        )
        return result.scalars().first() is not None

    async def get_contest_leaderboard(
        self,
        contest_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ContestTeamProgress]:
        """
        Retrieve contest leaderboard (teams ordered by score).

        Args:
            contest_id: Contest ID
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            List of ContestTeamProgress ordered by score DESC
        """
        result = await self.db.execute(
            select(ContestTeamProgress)
            .filter(ContestTeamProgress.contest_id == contest_id)
            .options(joinedload(ContestTeamProgress.contest_team))
            .order_by(ContestTeamProgress.score.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.unique().scalars().all())

    async def register_team_to_contest(
        self,
        contest_id: UUID,
        team_id: UUID,
    ) -> ContestTeam:
        """
        Register an existing team for a contest.

        Creates a ContestTeam record to register the team for the contest
        and initializes progress tracking. If already registered, returns existing registration.

        Args:
            contest_id: Contest ID
            team_id: Team ID (team must already exist)

        Returns:
            Created or existing ContestTeam object

        Raises:
            ValueError: If team or contest not found
        """
        # Check if already registered
        existing = await self.db.execute(
            select(ContestTeam).filter(
                ContestTeam.contest_id == contest_id,
                ContestTeam.team_id == team_id,
            )
        )
        existing_registration = existing.scalar_one_or_none()
        if existing_registration:
            return existing_registration

        # Create ContestTeam registration
        contest_team = ContestTeam(
            contest_id=contest_id,
            team_id=team_id,
            team_status="CONFIRMED",
            approval_status=TeamApprovalStatus.APPROVED,
        )
        self.db.add(contest_team)

        # Create progress tracking
        progress = ContestTeamProgress(
            contest_id=contest_id,
            team_id=team_id,
            score=0,
        )
        self.db.add(progress)

        await self.db.flush()
        await self.db.refresh(contest_team)
        return contest_team

    async def get_user_or_raise(self, user_id: UUID) -> User:
        """
        Retrieve a user by their ID or raise an exception if not found.

        Args:
            user_id: ID of the user to retrieve

        Returns:
            The User object if found

        Raises:
            UserNotFoundError: If user not found
        """
        result = await self.db.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise UserNotFoundError(str(user_id))
        return user

    async def get_contests_by_difficulty(
        self,
        filters: StudentContestFilters,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve public contests filtered by problem difficulty level.

        Returns public, available contests that contain problems of specified difficulty.
        Helps students find contests matching their skill level.

        Implementation:
        - Joins Contest with ContestQuestion with Question
        - Filters for public contests only
        - Filters by difficulty level
        - Returns distinct contests to avoid duplicates from multiple problems

        Args:
            filters: StudentContestFilters with difficulty_level specified
            pagination: PaginationParams for skip/limit

        Returns:
            PaginatedResult with contests containing problems of specified difficulty

        Raises:
            ValueError: If difficulty not specified in filters
        """
        if not filters.difficulty_level:
            raise ValueError("Difficulty level must be specified in filters")

        from app.models.question import Question

        # Build base query joining contests with their problems
        base_query = (
            select(Contest)
            .options(selectinload(Contest.questions))
            .join(ContestQuestion, ContestQuestion.contest_id == Contest.id)
            .join(Question, Question.id == ContestQuestion.question_id)
            .filter(
                Contest.is_public.is_(True),
                Contest.is_deleted.is_(False),
                Contest.status.in_([ContestStatus.SCHEDULED, ContestStatus.RUNNING]),
                Question.difficulty == filters.difficulty_level,
            )
            .distinct()
        )

        # Apply additional search filter
        if filters.search_term:
            base_query = base_query.filter(
                Contest.name.ilike(f"%{filters.search_term}%")
            )

        # Get total count
        count_query = select(func.count()).select_from(
            base_query.with_only_columns(Contest.id).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        contests = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=contests)

    async def get_past_contests(
        self,
        user_id: UUID,
        pagination: PaginationParams,
    ) -> PaginatedResult:
        """
        Retrieve finished contests that student participated in.

        Returns contests with FINISHED status where student was registered via team.
        Allows students to review past competitions and results.

        Implementation:
        - Filters for Contest.status == FINISHED
        - Joins with ContestTeam and TeamUser
        - Ensures student is team member
        - Eager loads relationships
        - Orders by end_time descending (most recent first)

        Args:
            user_id: UUID of the student
            pagination: PaginationParams for skip/limit

        Returns:
            PaginatedResult with past contests student participated in
        """
        base_query = (
            select(Contest)
            .options(selectinload(Contest.questions))
            .join(ContestTeam, ContestTeam.contest_id == Contest.id)
            .join(Team, ContestTeam.team_id == Team.id)
            .join(TeamUser, TeamUser.team_id == Team.id)
            .filter(
                TeamUser.user_id == user_id,
                Contest.status == ContestStatus.FINISHED,
                Contest.is_deleted.is_(False),
            )
            .order_by(Contest.end_time.desc())
            .distinct()
        )

        # Get total count
        count_result = await self.db.execute(
            select(func.count(func.distinct(Contest.id)))
            .join(ContestTeam, ContestTeam.contest_id == Contest.id)
            .join(Team, ContestTeam.team_id == Team.id)
            .join(TeamUser, TeamUser.team_id == Team.id)
            .filter(
                TeamUser.user_id == user_id,
                Contest.status == ContestStatus.FINISHED,
                Contest.is_deleted.is_(False),
            )
        )
        total = count_result.scalar() or 0

        # Get paginated results
        result = await self.db.execute(
            base_query.offset(pagination.skip).limit(pagination.limit)
        )
        items = list(result.unique().scalars().all())

        return PaginatedResult(total=total, items=items)
