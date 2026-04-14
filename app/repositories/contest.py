from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.contest import ContestNotFoundError, InstructorNotAssignedError
from app.exceptions.user import UserNotFoundError
from app.models.contest import Contest, ContestInstructor, ContestQuestion
from app.models.question import Question, QuestionLanguage, TestCase
from app.models.tag import QuestionTag
from app.models.user import User
from app.repositories.dto import (
    ContestFilters,
    PaginatedResult,
    PaginationParams,
)
from app.repositories.dto.contest import ContestQuestionFilters
from app.repositories.dto.contest_question import (
    AddContestQuestionData,
    RemoveContestQuestionData,
)
from app.utils.enums import ContestStatus


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

    async def is_question_in_contest(self, contest_id: UUID, question_id: UUID) -> bool:
        """
        Check if a question is already added to a contest.

        This method is optimized to return early with a single database query.

        Args:
            contest_id: ID of the contest.
            question_id: ID of the question.

        Returns:
            True if the question is in the contest, False otherwise.
        """
        result = await self.db.execute(
            select(ContestQuestion).filter(
                ContestQuestion.contest_id == contest_id,
                ContestQuestion.question_id == question_id,
            )
        )
        return result.scalars().first() is not None

    async def add_question_to_contest(
        self, data: AddContestQuestionData
    ) -> ContestQuestion:
        """
        Add a question to a contest.

        Creates a new ContestQuestion relationship with the specified metadata.
        Assumes all validation has been completed before this call.

        Args:
            data: AddContestQuestionData containing contest_id, question_id, order,
                  duration, score, and created_by.

        Returns:
            The created ContestQuestion entity.

        Raises:
            N/A: All validation is performed in the service layer.

        Complexity:
            - Time: O(1) single INSERT query
            - Space: O(1)
        """
        from app.mappers.contest_question import build_contest_question_entity

        contest_question = build_contest_question_entity(data)
        self.db.add(contest_question)
        await self.db.flush()
        return contest_question

    async def remove_question_from_contest(
        self, data: RemoveContestQuestionData
    ) -> None:
        """
        Remove a question from a contest.

        Deletes the ContestQuestion relationship, cascading as defined in the model.

        Args:
            data: RemoveContestQuestionData containing contest_id and question_id.

        Raises:
            N/A: The caller is responsible for checking existence before removal.

        Complexity:
            - Time: O(1) single DELETE query
            - Space: O(1)
        """
        result = await self.db.execute(
            select(ContestQuestion).filter(
                ContestQuestion.contest_id == data.contest_id,
                ContestQuestion.question_id == data.question_id,
            )
        )
        contest_question = result.scalars().first()
        if contest_question:
            await self.db.delete(contest_question)
            await self.db.flush()

    async def get_contest_questions_paginated(
        self,
        contest_id: UUID,
        pagination: PaginationParams,
        filters: ContestQuestionFilters | None = None,
    ) -> PaginatedResult:
        """
        Retrieve questions in a contest with pagination and filters.

        Args:
            contest_id: ID of the contest.
            pagination: Pagination parameters with skip and limit.
            filters: Optional search and metadata filters.

        Returns:
            PaginatedResult containing Question entities.
        """
        filters = filters or ContestQuestionFilters()

        base_query = (
            select(Question)
            .join(ContestQuestion, ContestQuestion.question_id == Question.id)
            .options(
                selectinload(Question.languages).selectinload(
                    QuestionLanguage.language
                ),
                selectinload(Question.tags),
                selectinload(Question.testcases),
            )
            .filter(ContestQuestion.contest_id == contest_id)
        )

        if filters.search_term:
            base_query = base_query.filter(
                Question.question_text.ilike(f"%{filters.search_term}%")
            )

        if filters.difficulty is not None:
            base_query = base_query.filter(Question.difficulty == filters.difficulty)

        if filters.language_id is not None:
            base_query = base_query.filter(
                exists(
                    select(1).where(
                        QuestionLanguage.question_id == Question.id,
                        QuestionLanguage.language_id == filters.language_id,
                    )
                )
            )

        if filters.tag_id is not None:
            base_query = base_query.filter(
                exists(
                    select(1).where(
                        QuestionTag.question_id == Question.id,
                        QuestionTag.tag_id == filters.tag_id,
                    )
                )
            )

        filtered_query = base_query

        count_query = select(func.count()).select_from(
            filtered_query.with_only_columns(Question.id).order_by(None).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        paged_query = filtered_query.order_by(ContestQuestion.order, Question.id)

        result = await self.db.execute(
            paged_query.offset(pagination.skip).limit(pagination.limit)
        )
        questions = list(result.unique().scalars().all())

        if questions:
            question_ids = [question.id for question in questions]
            count_result = await self.db.execute(
                select(TestCase.question_id, func.count(TestCase.id))
                .where(TestCase.question_id.in_(question_ids))
                .group_by(TestCase.question_id)
            )
            testcase_counts = {
                question_id: count for question_id, count in count_result.all()
            }
            for question in questions:
                setattr(question, "testcase_count", testcase_counts.get(question.id, 0))

        return PaginatedResult(total=total, items=questions)

    async def add_questions_to_contest(
        self, data_list: list[AddContestQuestionData]
    ) -> list[ContestQuestion]:
        """
        Batch add multiple questions to a contest.

        Creates multiple ContestQuestion relationships in a single batch operation.
        All validation has been completed before this call.

        Args:
            data_list: List of AddContestQuestionData objects.

        Returns:
            List of created ContestQuestion entities.

        Complexity:
            - Time: O(n) where n is the number of questions (single INSERT with multiple values)
            - Space: O(n)
        """
        from app.mappers.contest_question import build_contest_question_entity

        contest_questions = []
        for data in data_list:
            contest_question = build_contest_question_entity(data)
            contest_questions.append(contest_question)
            self.db.add(contest_question)

        await self.db.flush()
        return contest_questions

    async def remove_questions_from_contest(
        self, contest_id: UUID, question_ids: list[UUID]
    ) -> None:
        """
        Batch remove multiple questions from a contest.

        Deletes multiple ContestQuestion relationships in a single batch delete operation.

        Args:
            contest_id: UUID of the contest.
            question_ids: List of question IDs to remove.

        Complexity:
            - Time: O(n) where n is the number of question IDs (single DELETE with IN clause)
            - Space: O(1)
        """
        if not question_ids:
            return

        delete_query = select(ContestQuestion).filter(
            ContestQuestion.contest_id == contest_id,
            ContestQuestion.question_id.in_(question_ids),
        )
        result = await self.db.execute(delete_query)
        contest_questions = result.scalars().all()

        for cq in contest_questions:
            await self.db.delete(cq)

        if contest_questions:
            await self.db.flush()
