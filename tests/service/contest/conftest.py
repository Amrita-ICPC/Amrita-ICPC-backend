"""Contest service test fixtures and configuration.

This module provides specialized fixtures for testing contest-related functionality.
It includes mocked dependencies, domain objects, and helper fixtures that
simplify test setup and ensure consistent test behavior.

The fixtures follow a hierarchy:
- Dependency mocks (repository, guard, validator, user_repository)
- Service instances with injected dependencies
- Domain object mocks (Contest, ContestInstructor, User)
- Schema fixtures (DTOs and responses)
- Helper setup fixtures for common scenarios
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.guards.contest import ContestOperationGuard
from app.models.contest import Contest, ContestInstructor
from app.models.user import User
from app.repositories.audience import AudienceRepository
from app.repositories.contest import ContestRepository
from app.repositories.question import QuestionRepository
from app.repositories.user import UserRepository
from app.schema.contest import ContestCreate, ContestUpdate
from app.service.contest_service import ContestService
from app.utils.enums import (
    ContestMode,
    ContestStatus,
    ContestTeamParticipationType,
    ScoringType,
    TeamApprovalMode,
    UserRole,
)
from app.validators.contest import ContestValidator

# Patch cache decorators to disable Redis access in tests
patch("app.core.cache.decorators.cache_get", lambda **kw: lambda f: f).start()
patch("app.core.cache.decorators.cache_set", lambda **kw: lambda f: f).start()
patch("app.core.cache.decorators.cache_delete", lambda **kw: lambda f: f).start()


@pytest.fixture
def mock_contest_repository():
    """Mock ContestRepository with all database operations mocked.

    All methods return AsyncMock objects by default. Individual tests
    can override specific method behaviors by setting return_value or side_effect.

    Returns:
        AsyncMock: Mock ContestRepository instance
    """
    mock_repo = AsyncMock(spec=ContestRepository)
    mock_repo.db = AsyncMock()
    return mock_repo


@pytest.fixture
def mock_user_repository():
    """Mock UserRepository for user-related database operations.

    All methods return AsyncMock objects by default. Tests can override
    specific method behaviors as needed.

    Returns:
        AsyncMock: Mock UserRepository instance
    """
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def mock_guard():
    """Mock ContestOperationGuard for permission validation.

    All permission checks pass silently by default. Tests can simulate
    permission denial by setting side_effect on specific methods.

    Returns:
        AsyncMock: Mock ContestOperationGuard instance
    """
    return AsyncMock(spec=ContestOperationGuard)


@pytest.fixture
def mock_validator():
    """Mock ContestValidator for business rule validation.

    All validations pass silently by default. Tests can simulate
    validation failures by setting side_effect on specific methods.

    Returns:
        AsyncMock: Mock ContestValidator instance
    """
    return AsyncMock(spec=ContestValidator)


@pytest.fixture
def mock_audience_repository():
    """Mock AudienceRepository for audience-related data access.

    Returns:
        AsyncMock: Mock AudienceRepository instance
    """
    return AsyncMock(spec=AudienceRepository)


@pytest.fixture
def mock_question_repository():
    """Mock QuestionRepository for contest question data access.

    Returns:
        AsyncMock: Mock QuestionRepository instance
    """
    return AsyncMock(spec=QuestionRepository)


@pytest.fixture
def contest_service(
    mock_contest_repository,
    mock_user_repository,
    mock_guard,
    mock_validator,
    mock_audience_repository,
    mock_question_repository,
):
    """ContestService instance with all dependencies mocked.

    Provides a fully configured ContestService with mocked dependencies,
    ready for testing business logic without database operations.

    Args:
        mock_contest_repository: Mock ContestRepository
        mock_user_repository: Mock UserRepository
        mock_guard: Mock ContestOperationGuard
        mock_validator: Mock ContestValidator
        mock_audience_repository: Mock AudienceRepository
        mock_question_repository: Mock QuestionRepository

    Returns:
        ContestService: Service instance with mocked dependencies
    """
    return ContestService(
        repository=mock_contest_repository,
        user_repository=mock_user_repository,
        guard=mock_guard,
        validator=mock_validator,
        audience_repository=mock_audience_repository,
    )


@pytest.fixture
def mock_contest(user_id):
    """Mock Contest ORM object with typical attributes.

    Creates a realistic contest with:
    - Unique ID
    - Name, description, image
    - Date range (start/end, registration start/end)
    - Team size constraints
    - Scoring type and status
    - Creator information
    - Soft delete fields

    Args:
        user_id: UUID from global fixture (contest creator)

    Returns:
        AsyncMock: Mock Contest object
    """
    now = datetime.now(timezone.utc)
    contest = AsyncMock(spec=Contest)
    contest.id = __import__("uuid").uuid4()
    contest.name = "Test Contest"
    contest.description = "Test contest description"
    contest.image = None
    contest.is_public = True
    contest.start_time = now + timedelta(days=1)
    contest.end_time = now + timedelta(days=2)
    contest.registration_start = now
    contest.registration_end = now + timedelta(hours=1)
    contest.max_teams = None
    contest.min_team_size = 1
    contest.max_team_size = 5
    contest.rules = None
    contest.scoring_type = ScoringType.AUTO
    contest.team_approval_mode = TeamApprovalMode.AUTO_APPROVE
    contest.contest_mode = ContestMode.INDIVIDUAL
    contest.status = ContestStatus.DRAFT
    contest.published_at = None
    contest.published_by = None
    contest.show_leaderboard_during_contest = False
    contest.participation_type = ContestTeamParticipationType.LEADER_ONLY
    contest.results_published_at = None
    contest.show_leaderboard = False
    contest.show_team_submissions = False
    contest.is_deleted = False
    contest.deleted_at = None
    contest.deleted_by = None
    contest.created_by = user_id
    contest.created_at = now
    contest.updated_at = now
    contest.updated_by = None
    contest.duration = None
    return contest


@pytest.fixture
def mock_user():
    """Mock User object with student role.

    Returns:
        AsyncMock: Mock User object with typical student attributes
    """
    user = AsyncMock(spec=User)
    user.id = __import__("uuid").uuid4()
    user.name = "Test User"
    user.email = "test@example.com"
    user.role = UserRole.student
    return user


@pytest.fixture
def mock_instructor(user_id):
    """Mock User object with instructor role.

    Args:
        user_id: Can be any UUID, used as instructor ID

    Returns:
        AsyncMock: Mock User object with instructor attributes
    """
    from datetime import date, datetime

    user = AsyncMock(spec=User)
    user.id = user_id
    user.user_id = "instructor_001"
    user.name = "Test Instructor"
    user.email = "instructor@example.com"
    user.phone_no = "+1234567890"
    user.role = UserRole.instructor
    user.gender = "male"
    user.dob = date(1990, 1, 1)
    user.created_at = datetime(2024, 1, 1, 0, 0, 0)
    return user


@pytest.fixture
def mock_contest_instructor(mock_contest, mock_instructor):
    """Mock ContestInstructor linking a contest and instructor.

    Args:
        mock_contest: Mock Contest object
        mock_instructor: Mock User object with instructor role

    Returns:
        AsyncMock: Mock ContestInstructor with relationships
    """
    contest_instructor = AsyncMock(spec=ContestInstructor)
    contest_instructor.contest_id = mock_contest.id
    contest_instructor.instructor_id = mock_instructor.id
    contest_instructor.contest = mock_contest
    contest_instructor.instructor = mock_instructor
    return contest_instructor


@pytest.fixture
def contest_create_data():
    """Default ContestCreate DTO for testing.

    Provides a standard contest creation request with all fields.
    Individual tests can override or modify as needed.

    Returns:
        ContestCreate: Standard contest creation DTO
    """
    now = datetime.now(timezone.utc)
    return ContestCreate(
        name="Test Contest",
        description="Test contest description",
        image=None,
        is_public=True,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=2),
        registration_start=now,
        registration_end=now + timedelta(hours=1),
        max_teams=None,
        min_team_size=1,
        max_team_size=5,
        rules=None,
        scoring_type=ScoringType.AUTO,
    )


@pytest.fixture
def contest_update_data():
    """Default ContestUpdate DTO for testing.

    Provides a standard contest update request with optional fields.
    Individual tests can override or modify as needed.

    Returns:
        ContestUpdate: Standard contest update DTO
    """
    return ContestUpdate(
        name="Updated Contest Name",
        description="Updated description",
        is_public=True,
    )


@pytest.fixture
def setup_valid_contest(mock_contest_repository, mock_contest):
    """Pre-configure repository to return a valid contest.

    Use this fixture when contest existence is not the focus of the test.
    Skip when testing ContestNotFoundError scenarios.

    Args:
        mock_contest_repository: Mock ContestRepository
        mock_contest: Mock Contest object

    Returns:
        AsyncMock: The configured mock contest

    Example:
        def test_foo(contest_service, setup_valid_contest, ...):
            # Contest already configured, proceed with test logic
            pass
    """
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.get_creator.return_value = None
    return mock_contest


@pytest.fixture
def setup_valid_contest_with_creator(
    mock_contest_repository, mock_user_repository, mock_contest, mock_user
):
    """Pre-configure repository for valid contest with creator user.

    Use in tests that need both contest and creator information.

    Args:
        mock_contest_repository: Mock ContestRepository
        mock_user_repository: Mock UserRepository
        mock_contest: Mock Contest object
        mock_user: Mock User object with student role

    Returns:
        tuple: (mock_contest, mock_user) for direct access

    Example:
        def test_something(contest_service, setup_valid_contest_with_creator):
            mock_contest, mock_user = setup_valid_contest_with_creator
            # Both are configured
    """
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_user_or_raise.return_value = mock_user
    return mock_contest, mock_user


@pytest.fixture
def setup_valid_contest_with_instructors(
    mock_contest_repository, mock_user_repository, mock_contest, mock_instructor
):
    """Pre-configure repository for valid contest with instructors.

    Use in tests involving instructor management.

    Args:
        mock_contest_repository: Mock ContestRepository
        mock_user_repository: Mock UserRepository
        mock_contest: Mock Contest object
        mock_instructor: Mock User with instructor role

    Returns:
        tuple: (mock_contest, mock_instructor) for direct access
    """
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_user_or_raise.return_value = mock_instructor
    return mock_contest, mock_instructor
