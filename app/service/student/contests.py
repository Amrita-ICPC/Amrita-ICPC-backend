"""Student-facing service for contest operations.

This service duplicates ContestService patterns for student-specific operations.
Follows exact architecture of ContestService but with student-only read semantics.

Architecture:
    - Repository Pattern: All database operations delegated to ContestRepository  
    - No Guard/Validator: Students have inherent read access
    - Cache Strategy: Results cached with appropriate TTLs and user context
    - Mapper Pattern: All ORM → DTO/Schema transformations via dedicated mappers

Key Responsibilities:
    - Query available contests (public, in registration window)
    - Query registered contests (student's teams enrolled in)
    - Get contest details with full problem list
    - Get contest problems  
    - Register team for contest
    - Filter contests by problem difficulty
    - Get past contests student participated in
    - Coordinate cache invalidation

Cache Strategy:
    - Available contests cached per user per filter/pagination
    - Registered contests cached per user per pagination
    - Contest details cached per user per contest  
    - Cache invalidated on registration operations
"""

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.student.contests import ContestNotFoundError
from app.mappers.student.contest_mappers import (
    to_student_available_contests_list_response,
    to_student_registered_contests_list_response,
    to_student_contest_details_response,
    to_student_contest_problems_list_response,
)
from app.repositories.dto import PaginationParams, StudentContestFilters
from app.schema.student.contests import (
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestProblemsListResponse,
    StudentContestRegistrationResponse,
)
from app.utils.enums import ContestStatus, QuestionDifficulty

if TYPE_CHECKING:
    from app.repositories.contest import ContestRepository
    from app.repositories.team import TeamRepository


def get_student_contest_key(contest_id: UUID, user_id: UUID) -> str:
    """Generate cache key for student contest view."""
    return f"student:contest:{contest_id}:user:{user_id}"


class StudentContestService:
    """Service layer for student contest operations.

    Orchestrates student-specific contest queries following ContestService patterns.
    Provides read-only semantics appropriate for student access level.

    Architecture:
        - Repository Pattern: All DB operations via ContestRepository
        - No Guard/Validator: Students have inherent read access to public contests
        - Cache Strategy: Per-user caching for permission-safe results
        - Mapper Pattern: ORM objects transformed via dedicated mappers

    Dependencies:
        - ContestRepository: Contest data access
        - TeamRepository: Team membership verification

    Cache Strategy:
        - Available contests: Per user per filters
        - Registered contests: Per user per pagination
        - Contest details: Per user per contest
        - Cache invalidated on registration
    """

    def __init__(
        self,
        contest_repository: "ContestRepository",
        team_repository: "TeamRepository",
    ):
        self.contest_repository = contest_repository
        self.team_repository = team_repository

    @cache_get(
        key_builder=lambda self, user_id, search_term=None, skip=0, limit=10: (
            f"student:contests:available:user:{user_id}:search:{search_term}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_available_contests(
        self,
        user_id: UUID,
        search_term: str | None = None,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentContestListResponse:
        """
        Get all public, available contests student can register for.

        Retrieves contests matching student-appropriate criteria:
        - Contest is public
        - Contest is in SCHEDULED or RUNNING status
        - Not soft-deleted
        - Registration window is open

        Implementation:
        - Delegates filtering to repository
        - Applies pagination
        - Returns transformed response

        Args:
            user_id: UUID of the student
            search_term: Optional text search in contest names
            skip: Pagination skip
            limit: Pagination limit

        Returns:
            StudentContestListResponse with available contests

        Cache Behavior:
            - Cached per user including search/pagination
            - TTL: 300 seconds
        """
        filters = StudentContestFilters(search_term=search_term)
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.contest_repository.get_available_contests_for_student(
            filters=filters, pagination=pagination
        )

        logger.info(
            f"Student {user_id} queried available contests (found: {result.total})"
        )
        return to_student_available_contests_list_response(result, skip, limit)

    @cache_get(
        key_builder=lambda self, user_id, skip=0, limit=10: (
            f"student:contests:registered:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_registered_contests(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentContestListResponse:
        """
        Get all contests student is registered for (via team membership).

        Retrieves contests where student's team is registered via ContestTeam.
        Includes registration timestamp and team status.

        Implementation:
        - Queries via ContestTeam → TeamUser relationship
        - Joins with Contest for details
        - Orders by most recent registration
        - Applies pagination

        Args:
            user_id: UUID of the student
            skip: Pagination skip
            limit: Pagination limit

        Returns:
            StudentContestListResponse with registered contests

        Cache Behavior:
            - Cached per user including pagination
            - TTL: 300 seconds
        """
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.contest_repository.get_registered_contests_for_student(
            user_id=user_id, pagination=pagination
        )

        logger.info(
            f"Student {user_id} queried registered contests (found: {result.total})"
        )
        return to_student_registered_contests_list_response(result, skip, limit)

    @cache_get(
        key_builder=lambda self, contest_id, user_id: get_student_contest_key(
            contest_id, user_id
        ),
        ttl=300,
    )
    async def get_contest_by_id(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestDetailsResponse:
        """
        Get complete contest details with all problems.

        Retrieves full contest information:
        - Contest metadata (name, dates, rules, team config)
        - All problems with details
        - Student registration status
        - Team requirements and approval mode

        Visibility:
        - Public contests: All students can view
        - Private contests: Only registered students
        - Soft-deleted: Nobody

        Implementation:
        - Validates contest exists and not soft-deleted
        - Checks student registration status
        - Fetches problems via repository
        - Transforms to detailed response

        Args:
            contest_id: UUID of contest
            user_id: UUID of student viewing

        Returns:
            StudentContestDetailsResponse with full contest details

        Raises:
            ContestNotFoundError: If not found or soft-deleted

        Cache Behavior:
            - Cached per user per contest
            - TTL: 300 seconds
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Check if student is registered
        is_registered = await self.contest_repository.is_student_registered(
            contest_id, user_id
        )

        # Fetch problems
        problems = await self.contest_repository.get_contest_problems(contest_id)

        logger.info(f"Student {user_id} viewed contest {contest_id}")
        return to_student_contest_details_response(
            contest, problems, is_registered, user_id
        )

    @cache_get(
        key_builder=lambda self, contest_id, user_id: (
            f"student:contest:{contest_id}:problems:user:{user_id}"
        ),
        ttl=300,
    )
    async def get_contest_problems(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestProblemsListResponse:
        """
        Get list of problems in a contest.

        Retrieves all problems for a contest ordered by position.
        Includes difficulty, score, and time limit for each problem.

        Implementation:
        - Validates contest exists
        - Fetches problems via repository
        - Transforms to response format
        - Returns ordered list

        Args:
            contest_id: UUID of contest
            user_id: UUID of student viewing

        Returns:
            StudentContestProblemsListResponse with problem list

        Raises:
            ContestNotFoundError: If contest not found

        Cache Behavior:
            - Cached per user per contest
            - TTL: 300 seconds
        """
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        problems = await self.contest_repository.get_contest_problems(contest_id)

        logger.info(
            f"Student {user_id} viewed problems for contest {contest_id} (count: {len(problems)})"
        )
        return to_student_contest_problems_list_response(contest, problems)

    @cache_delete(
        key_builder=lambda self, contest_id, team_id, user_id: [
            f"student:contests:available:user:{user_id}:*",
            f"student:contests:registered:user:{user_id}:*",
            get_student_contest_key(contest_id, user_id),
        ]
    )
    async def register_team_for_contest(
        self, contest_id: UUID, team_id: UUID, user_id: UUID
    ) -> StudentContestRegistrationResponse:
        """
        Register a student's team for a contest.

        Registers an existing team (that student is a member of) for a contest.
        Sets approval status based on contest settings (AUTO_APPROVE or INSTRUCTOR_REVIEW).

        Validation Flow:
        1. Verify contest exists and not soft-deleted
        2. Verify team exists and not soft-deleted
        3. Verify user is a member of the team (critical!)
        4. Create ContestTeam record
        5. Invalidate student's contest caches

        Business Rules:
        1. User MUST be team member (cannot register others' teams)
        2. Team MUST exist
        3. Contest MUST exist and be in registration window
        4. Cannot register same team twice

        Args:
            contest_id: UUID of contest
            team_id: UUID of team
            user_id: UUID of student (must be team member)

        Returns:
            StudentContestRegistrationResponse with registration status

        Raises:
            ContestNotFoundError: If contest not found
            TeamNotFoundError: If team not found
            PermissionDeniedError: If user not team member

        Cache Behavior:
            - Invalidates all contest caches for student
        """
        # Step 1: Verify contest exists
        contest = await self.contest_repository.get_contest_or_raise(contest_id)

        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Step 2: Verify team exists
        team = await self.team_repository.get_team_or_raise(team_id)

        # Step 3: CRITICAL - Verify user is team member
        is_team_member = await self.team_repository.is_student_in_team(team_id, user_id)
        if not is_team_member:
            raise PermissionDeniedError(
                "You can only register for contests with teams you are a member of"
            )

        # Step 4: Register team for contest
        await self.contest_repository.register_team_to_contest(
            contest_id=contest_id, team_id=team_id
        )

        logger.info(
            f"User {user_id} registered team {team_id} for contest {contest_id}"
        )

        return StudentContestRegistrationResponse(
            message="Successfully registered for contest",
            contest_id=contest_id,
            team_id=team_id,
            status="success",
        )

    @cache_get(
        key_builder=lambda self, user_id, difficulty=None, skip=0, limit=10: (
            f"student:contests:difficulty:{difficulty}:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_contests_by_difficulty(
        self,
        user_id: UUID,
        difficulty: str,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentContestListResponse:
        """
        Get contests filtered by problem difficulty level.

        Retrieves public contests containing problems of specific difficulty.
        Helps students find contests matching their skill level.

        Difficulty is validated against QuestionDifficulty enum.

        Args:
            user_id: UUID of student
            difficulty: Difficulty level (EASY, MEDIUM, HARD)
            skip: Pagination skip
            limit: Pagination limit

        Returns:
            StudentContestListResponse with difficulty-filtered contests

        Raises:
            ValueError: If difficulty is invalid

        Cache Behavior:
            - Cached per user per difficulty
            - TTL: 300 seconds
        """
        # Validate difficulty enum
        try:
            _ = QuestionDifficulty(difficulty)
        except ValueError:
            raise ValueError(
                f"Invalid difficulty: {difficulty}. Must be one of {[d.value for d in QuestionDifficulty]}"
            )

        filters = StudentContestFilters(difficulty_level=difficulty)
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.contest_repository.get_contests_by_difficulty(
            filters=filters, pagination=pagination
        )

        logger.info(
            f"Student {user_id} viewed contests by difficulty: {difficulty} (found {result.total})"
        )

        return to_student_available_contests_list_response(result, skip, limit)

    @cache_get(
        key_builder=lambda self, user_id, skip=0, limit=10: (
            f"student:contests:past:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
        ttl=300,
    )
    async def get_past_contests(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentContestListResponse:
        """
        Get finished contests student participated in.

        Retrieves contests with FINISHED status that student was registered for.
        Allows returning viewing results and learning from past competitions.

        Implementation:
        - Filters for ContestStatus.FINISHED
        - Checks student registration via ContestTeam
        - Orders by end_time descending
        - Applies pagination

        Args:
            user_id: UUID of student
            skip: Pagination skip
            limit: Pagination limit

        Returns:
            StudentContestListResponse with finished contests

        Cache Behavior:
            - Cached per user including pagination
            - TTL: 300 seconds
        """
        filters = StudentContestFilters(status=ContestStatus.FINISHED)
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.contest_repository.get_past_contests_for_student(
            user_id=user_id, filters=filters, pagination=pagination
        )

        logger.info(f"Student {user_id} viewed past contests (found {result.total})")

        return to_student_registered_contests_list_response(result, skip, limit)
