"""Student-facing service for contest operations.

This service orchestrates student contest-related business logic by coordinating
between the repository layer (data access) and schema layer (response formatting).
It focuses on read and registration operations available to students.

Architecture:
    - Repository Pattern: All database operations delegated to ContestRepository
    - No direct database access: Service layer remains database-agnostic
    - Cache Strategy: Results cached with appropriate TTLs and cache keys

Key Responsibilities:
    - Query available contests
    - Query registered contests
    - Get contest details with problem lists
    - Filter contests by difficulty
    - Get past contests student participated in
    - Register students for contests with teams
    - Transform repository data to API response schemas
    - Coordinate cache invalidation for contest-related data
"""

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get
from app.core.logger import logger
from app.core.permissions import ContestPermission
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.student.contests import ContestNotFoundError
from app.mappers.student.contest_mappers import (
    to_student_available_contests_list_response,
    to_student_contest_details_response,
    to_student_contest_problems_list_response,
    to_student_registered_contests_list_response,
)
from app.repositories.dto import PaginationParams, StudentContestFilters
from app.repositories.team import TeamRepository
from app.schema.student.contests import (
    StudentContestDetailsResponse,
    StudentContestListResponse,
    StudentContestProblemsListResponse,
    StudentContestRegistrationResponse,
    StudentRegisteredContestListResponse,
)
from app.utils.enums import ContestStatus, QuestionDifficulty

if TYPE_CHECKING:
    from app.repositories.contest import ContestRepository


def get_student_contest_key(contest_id: UUID, user_id: UUID) -> str:
    """Generate cache key for student contest view."""
    return f"student:contest:{contest_id}:user:{user_id}"


class StudentContestService:
    """Service layer for student contest operations.

    Orchestrates student-specific contest queries and registration operations.
    Enforces read-only semantics and provides filtered views appropriate for students.

    Architecture:
        - Repository Pattern: All database operations delegated to ContestRepository
        - No Guard/Validator: Students have inherent read access to contests
        - Cache Strategy: Individual and list queries cached with user context

    Key Methods:
        - get_available_contests: Query public contests in registration window
        - get_registered_contests: Query contests student is enrolled in
        - get_contest_details: Get full contest details with problem list
        - get_contest_problems: Get problem list for a contest
        - get_contests_by_difficulty: Filter contests by problem difficulty (EASY, MEDIUM, HARD)
        - get_past_contests: Get finished contests student participated in
        - register_for_contest: Register student's team for a contest

    Cache Strategy:
        - Available contests cached per user (includes filters)
        - Registered contests cached per user
        - Contest details cached per user per contest
        - Difficulty-filtered contests cached per difficulty
        - Past contests cached per user
        - Cache invalidated on registration operations
    """

    def __init__(
        self, contest_repository: "ContestRepository", team_repository: TeamRepository
    ):
        self.repository = contest_repository
        self.team_repository = team_repository

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=10,
        search_term=None,
        status=None: f"student:contests:available:user:{user_id}:search:{search_term}:status:{status}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_available_contests(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
        search_term: str | None = None,
        status: str | None = None,
    ) -> StudentContestListResponse:
        """
        Get all public, available contests that student can access and register for.

        Retrieves contests based on student-appropriate criteria:
        - Contest is public OR user is registered
        - Contest is in SCHEDULED or RUNNING status (not DRAFT or FINISHED)
        - Not soft-deleted
        - Includes problem count and team requirements

        Implementation:
        - Delegates filtering to repository for performance
        - Applies student-specific view filters
        - Returns paginated results with total count

        Args:
            user_id: UUID of the student requesting contests
            skip: Number of contests to skip for pagination (default: 0)
            limit: Maximum contests to return (default: 10, max: 100)
            search_term: Optional text to search in contest names
            status: Optional contest status filter

        Returns:
            StudentContestListResponse with paginated list of available contests

        Raises:
            None - Returns empty list if no contests found

        Cache Behavior:
            - Cached with user context to avoid showing registered contests
            - TTL: 300 seconds
        """
        parsed_status: ContestStatus | None = None
        if status is not None:
            parsed_status = ContestStatus(status)

        filters = StudentContestFilters(
            search_term=search_term,
            status=parsed_status,
            only_available=True,
        )
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.repository.get_available_contests_for_student(
            filters=filters, pagination=pagination
        )

        logger.info(
            f"Student {user_id} queried available contests (found: {result.total})"
        )
        return to_student_available_contests_list_response(result, skip, limit)

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=10: f"student:contests:registered:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_registered_contests(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentRegisteredContestListResponse:
        """
        Get all contests the student is registered for.

        Retrieves contests where student is a team member via ContestTeam.
        Includes registration timestamp, team information, and contest status.

        Implementation:
        - Queries via ContestTeam → TeamUser relationship
        - Joins with Contest for contest details
        - Returns ordered by registration date DESC

        Args:
            user_id: UUID of the student
            skip: Number of contests to skip for pagination (default: 0)
            limit: Maximum contests to return (default: 10, max: 100)

        Returns:
            StudentRegisteredContestListResponse with paginated registered contests

        Cache Behavior:
            - Cached per student with pagination context
            - TTL: 300 seconds
        """
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.repository.get_registered_contests_for_student(
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
    async def get_contest_details(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestDetailsResponse:
        """
        Get complete contest details with all problems and student registration status.

        Retrieves full contest information appropriate for student view:
        - Contest metadata (name, description, dates, rules)
        - Team configuration (min/max size, approval mode)
        - List of all problems with details
        - Current student registration status
        - Leaderboard availability flag

        Will only show contest if:
        - Contest is public, OR
        - Student is registered for contest, OR
        - Contest is not soft-deleted

        Implementation:
        - Fetches contest via repository
        - Fetches problems via separate repository call
        - Checks student registration status
        - Constructs detailed response with all nested data

        Args:
            contest_id: UUID of the contest
            user_id: UUID of the student viewing

        Returns:
            StudentContestDetailsResponse with full contest details and student context

        Raises:
            ContestNotFoundError: If contest doesn't exist or is soft-deleted

        Cache Behavior:
            - Cached per student per contest
            - TTL: 300 seconds
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Enforce domain-level permission check
        try:
            await ContestPermission.can_read_contest(
                self.repository.db,
                user_id=user_id,
                contest=contest,
            )
        except PermissionDeniedError:
            # Don't leak that the contest exists
            raise ContestNotFoundError(str(contest_id))

        # Check if student is registered
        is_registered = await self.repository.is_student_registered(contest_id, user_id)

        # Fetch problems
        problems = await self.repository.get_contest_problems(contest_id)

        logger.info(f"Student {user_id} viewed contest {contest_id} details")
        return to_student_contest_details_response(
            contest, problems, is_registered, user_id
        )

    @cache_get(
        key_builder=lambda self,
        contest_id,
        user_id: f"student:contest:{contest_id}:problems:user:{user_id}",
        ttl=300,
    )
    async def get_contest_problems(
        self, contest_id: UUID, user_id: UUID
    ) -> StudentContestProblemsListResponse:
        """
        Get list of problems in a contest for student view.

        Retrieves all problems in a contest ordered by position (order field).
        Includes problem metadata: difficulty, score, time limit.

        Implementation:
        - Validates contest exists
        - Fetches all problems via repository
        - Transforms to student response format
        - Returns ordered list

        Args:
            contest_id: UUID of the contest
            user_id: UUID of the student viewing (for logging)

        Returns:
            StudentContestProblemsListResponse with problem list and contest info

        Raises:
            ContestNotFoundError: If contest doesn't exist

        Cache Behavior:
            - Cached per student per contest
            - TTL: 300 seconds
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        problems = await self.repository.get_contest_problems(contest_id)

        logger.info(
            f"Student {user_id} queried problems for contest {contest_id} (count: {len(problems)})"
        )
        return to_student_contest_problems_list_response(contest, problems)

    @cache_delete(
        key_builder=lambda self, contest_id, team_id, user_id: [
            f"student:contests:available:user:{user_id}:*",
            f"student:contests:registered:user:{user_id}:*",
        ]
    )
    async def register_for_contest(
        self, contest_id: UUID, team_id: UUID, user_id: UUID
    ) -> StudentContestRegistrationResponse:
        """
        Register a student's team for a contest.

        Registers an existing team (that student is a member of) for a contest.
        Sets initial approval status based on contest settings:
        - AUTO_APPROVE: Approved immediately
        - INSTRUCTOR_REVIEW: Waiting for approval

        Business Rules:
        1. User MUST be a member of the team (cannot register other teams)
        2. Contest MUST exist and not be soft-deleted
        3. Team MUST exist and not be soft-deleted
        4. User can only register with a team (not individually)

        Registration Process:
        1. Validate contest exists and is not soft-deleted
        2. Validate team exists and is not soft-deleted
        3. Verify user is a member of the team
        4. Create ContestTeam record with appropriate approval status
        5. Invalidate student's contest list caches

        Implementation:
        - Verifies user is team member before allowing registration
        - Delegates to repository for contest_team creation
        - Sets team as CONFIRMED immediately
        - Returns registration response with status

        Args:
            contest_id: UUID of the contest to register for
            team_id: UUID of the team to register with
            user_id: UUID of the student registering (must be team member)

        Returns:
            StudentContestRegistrationResponse with registration status

        Raises:
            ContestNotFoundError: If contest not found or soft-deleted
            TeamNotFoundError: If team not found or soft-deleted
            PermissionDeniedError: If user is not a member of the team
            RegistrationWindowClosedError: If registration period has closed
            ContestAlreadyStartedError: If contest is already running/finished
            StudentAlreadyRegisteredError: If student already registered

        Cache Behavior:
            - Invalidates all available contests cache for student
            - Invalidates all registered contests cache for student
            - Invalidates specific contest details cache
        """
        contest = await self.repository.get_contest_or_raise(contest_id)

        if contest.is_deleted:
            raise ContestNotFoundError(str(contest_id))

        # Verify team exists
        await self.team_repository.get_team_or_raise(team_id)

        # CRITICAL: Verify user is a member of the team (cannot register other's teams)
        is_team_member = await self.team_repository.is_student_in_team(team_id, user_id)
        if not is_team_member:
            raise PermissionDeniedError(
                "You can only register for contests with teams you are a member of"
            )

        # Register team for contest
        await self.repository.register_team_to_contest(
            contest_id=contest_id, team_id=team_id
        )

        logger.info(
            f"User {user_id} registered team {team_id} for contest {contest_id}"
        )

        return StudentContestRegistrationResponse(
            message="Successfully registered for contest",
            contest_id=contest_id,
            status="success",
        )

    @cache_get(
        key_builder=lambda self,
        user_id,
        difficulty,
        skip=0,
        limit=10: f"student:contests:difficulty:{difficulty}:user:{user_id}:skip:{skip}:limit:{limit}",
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

        Retrieves all contests that contain problems of a specific difficulty level.
        Helps students find contests matching their skill level.

        Difficulty Levels:
        - EASY: Beginner-friendly contests
        - MEDIUM: Intermediate challenges
        - HARD: Advanced problems

        Query Process:
        1. Validate difficulty is valid enum value
        2. Find contests with problems of given difficulty
        3. Filter for public contests or those student is registered in
        4. Apply pagination
        5. Return filtered list

        Implementation:
        - Delegates to repository get_contests_by_difficulty
        - Auto-filters for public or registered contests
        - Respects pagination parameters
        - Caches results per user and difficulty

        Args:
            user_id: UUID of the student filtering contests
            difficulty: Difficulty level (EASY, MEDIUM, HARD)
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            StudentContestListResponse with contests matching difficulty

        Raises:
            InvalidDifficultyError: If difficulty value is invalid

        Cache Behavior:
            - Cached per user per difficulty level
            - TTL: 300 seconds
            - Cache key includes difficulty and pagination params
        """
        # Validate difficulty is valid enum value
        try:
            QuestionDifficulty(difficulty)
        except ValueError:
            raise ValueError(
                f"Invalid difficulty: {difficulty}. Must be one of {[d.value for d in QuestionDifficulty]}"
            )

        # Create filter for difficulty-based query
        filters = StudentContestFilters(difficulty_level=difficulty)
        pagination = PaginationParams(skip=skip, limit=limit)

        # Get contests by difficulty
        result = await self.repository.get_contests_by_difficulty(
            filters=filters,
            pagination=pagination,
        )

        logger.info(
            f"Student {user_id} viewed contests by difficulty: {difficulty} (found {result.total})"
        )

        return to_student_available_contests_list_response(result, skip, limit)

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=10: f"student:contests:past:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_past_contests(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> StudentRegisteredContestListResponse:
        """
        Get past contests (finished) that student participated in.

        Retrieves all contests with FINISHED status that the student was
        registered for. Allows students to review past competitions, see results,
        and learn from previous contests.

        Query Process:
        1. Get contests with status = FINISHED
        2. Filter for contests student was registered in
        3. Sort by end time (most recent first)
        4. Apply pagination
        5. Return paginated list

        Implementation:
        - Queries ContestStatus.FINISHED contests only
        - Checks student registration via ContestTeam relationship
        - Orders by contest.end_time descending
        - Includes problem counts and team info

        Args:
            user_id: UUID of the student requesting past contests
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            StudentContestListResponse with finished contests student participated in

        Cache Behavior:
            - Cached per user
            - TTL: 300 seconds
            - Cache key includes pagination params
        """
        # Create filter for finished contests only
        StudentContestFilters(status=ContestStatus.FINISHED)
        pagination = PaginationParams(skip=skip, limit=limit)

        # Get past contests student participated in
        result = await self.repository.get_past_contests(
            user_id=user_id,
            pagination=pagination,
        )

        logger.info(f"Student {user_id} viewed past contests (found {result.total})")

        return to_student_registered_contests_list_response(result, skip, limit)
