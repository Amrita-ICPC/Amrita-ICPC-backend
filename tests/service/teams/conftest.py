"""Team service test fixtures and configuration.

This module provides specialized fixtures for testing team-related functionality.
It includes mocked dependencies, domain objects, and helper fixtures that
simplify test setup and ensure consistent test behavior.

The fixtures follow a hierarchy:
- Dependency mocks (repository, guard, validator)
- Service instances with injected dependencies
- Domain object mocks (Team, Contest, User)
- Schema fixtures (DTOs and responses)
- Helper setup fixtures for common scenarios
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.guards.team import TeamOperationGuard
from app.models.contest import ContestTeam
from app.models.team import Team
from app.models.user import User
from app.repositories.team import TeamRepository
from app.repositories.contest import ContestRepository
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.user import UserRepository
from app.schema.team import ContestTeamResponse, TeamCreate
from app.service.team_service import TeamService
from app.utils.enums import TeamApprovalStatus, TeamStatus, UserRole
from app.validators.team import TeamValidator

patch("app.core.cache.decorators.cache_get", lambda **kw: lambda f: f).start()
patch("app.core.cache.decorators.cache_set", lambda **kw: lambda f: f).start()
patch("app.core.cache.decorators.cache_delete", lambda **kw: lambda f: f).start()


@pytest.fixture
def mock_repository():
    """Mock TeamRepository with all database operations mocked.

    All methods return AsyncMock objects by default. Individual tests
    can override specific method behaviors by setting return_value or side_effect.

    Returns:
        AsyncMock: Mock TeamRepository instance
    """
    mock = AsyncMock(spec=TeamRepository)
    # Add remove_team_members method (not yet in actual repository)
    mock.remove_team_members = AsyncMock()
    return mock


@pytest.fixture
def mock_guard():
    """Mock TeamOperationGuard for permission validation.

    All permission checks pass silently by default. Tests can simulate
    permission denial by setting side_effect on specific methods.

    Returns:
        AsyncMock: Mock TeamOperationGuard instance
    """
    return AsyncMock(spec=TeamOperationGuard)


@pytest.fixture
def mock_validator():
    """Mock TeamValidator for business rule validation.

    All validations pass silently by default. Tests can simulate
    validation failures by setting side_effect on specific methods.

    Returns:
        AsyncMock: Mock TeamValidator instance
    """
    return AsyncMock(spec=TeamValidator)


@pytest.fixture
def mock_contest_repository():
    return AsyncMock(spec=ContestRepository)


@pytest.fixture
def mock_user_repository():
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def mock_contest_team_repository():
    return AsyncMock(spec=ContestTeamRepository)


@pytest.fixture
def team_service(
    mock_repository,
    mock_contest_team_repository,
    mock_guard,
    mock_validator,
    mock_contest_repository,
):
    """TeamService instance with all dependencies mocked.

    Provides a fully configured TeamService with mocked dependencies,
    ready for testing business logic without database operations.

    Args:
        mock_repository: Mock TeamRepository
        mock_contest_team_repository: Mock ContestTeamRepository
        mock_guard: Mock TeamOperationGuard
        mock_validator: Mock TeamValidator
        mock_contest_repository: Mock ContestRepository

    Returns:
        TeamService: Service instance with mocked dependencies
    """
    mock_repository.get_contest_or_raise = mock_contest_repository.get_contest_or_raise

    mock_contest_team_repository.get_contest_teams = mock_repository.get_contest_teams
    mock_contest_team_repository.count_teams_by_status = mock_repository.get_team_status_counts
    if hasattr(mock_repository, "get_contest_team_by_id_or_raise"):
        mock_contest_team_repository.get_contest_team_by_id_or_raise = mock_repository.get_contest_team_by_id_or_raise
    elif hasattr(mock_repository, "get_contest_team_or_raise"):
        mock_contest_team_repository.get_contest_team_by_id_or_raise = mock_repository.get_contest_team_or_raise
    mock_contest_team_repository.get_contest_team_members.return_value = []

    return TeamService(
        repository=mock_repository,
        contest_team_repository=mock_contest_team_repository,
        contest_repository=mock_contest_repository,
        guard=mock_guard,
        validator=mock_validator,
    )


@pytest.fixture
def mock_team(leader_id):
    """Mock Team object with consistent leader assignment.

    The leader_id comes from the global conftest to ensure consistency
    with member_ids[0] across all tests.

    Args:
        leader_id: UUID from leader_id fixture

    Returns:
        AsyncMock: Mock Team object with typical attributes
    """
    team = AsyncMock(spec=Team)
    team.id = __import__("uuid").uuid4()
    team.name = "Test Team"
    team.description = "Test Description"
    team.logo = None
    team.leader_id = leader_id
    team.created_by = __import__("uuid").uuid4()
    return team


@pytest.fixture
def mock_contest_team(mock_contest, mock_team):
    """Mock ContestTeam linking a contest and team.

    Args:
        mock_contest: Mock Contest object
        mock_team: Mock Team object

    Returns:
        AsyncMock: Mock ContestTeam with relationships set
    """
    contest_team = AsyncMock(spec=ContestTeam)
    contest_team.id = __import__("uuid").uuid4()
    contest_team.contest_id = mock_contest.id
    contest_team.team_id = mock_team.id
    contest_team.team_status = TeamStatus.DRAFT
    contest_team.approval_status = TeamApprovalStatus.WAITING
    contest_team.team = mock_team
    return contest_team


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
def mock_users(member_ids):
    """Mock Users list with IDs matching member_ids fixture.

    This ensures team_data.member_ids and mock_users[i].id always match,
    preventing silent test failures from ID mismatches.

    Args:
        member_ids: List of UUIDs from member_ids fixture

    Returns:
        list[AsyncMock]: List of mock User objects with matching IDs
    """
    users = []
    for i, uid in enumerate(member_ids):
        user = AsyncMock(spec=User)
        user.id = uid
        user.name = f"User {i}"
        user.email = f"user{i}@example.com"
        user.role = UserRole.student
        users.append(user)
    return users


@pytest.fixture
def team_data(member_ids, leader_id):
    """Default TeamCreate DTO for testing.

    Provides a standard team creation request with DRAFT status.
    Individual tests can override or modify as needed.

    Args:
        member_ids: List of member UUIDs
        leader_id: Leader UUID (first member)

    Returns:
        TeamCreate: Standard team creation DTO
    """
    return TeamCreate(
        name="Test Team",
        description="Test team description",
        logo=None,
        leader_id=leader_id,
        member_ids=member_ids,
        status=TeamStatus.DRAFT,
    )


@pytest.fixture
def mock_contest_team_response():
    """Mock ContestTeamResponse for service method returns.

    Simple mock that prevents schema validation issues during testing.

    Returns:
        AsyncMock: Mock response object
    """
    return AsyncMock(spec=ContestTeamResponse)


@pytest.fixture
def setup_valid_contest(mock_repository, mock_contest):
    """Pre-configure repository to return a valid contest.

    Use this fixture when contest existence is not the focus of the test.
    Skip when testing ContestNotFoundError scenarios.

    Args:
        mock_repository: Mock TeamRepository
        mock_contest: Mock Contest object

    Returns:
        AsyncMock: The configured mock contest

    Example:
        def test_foo(team_service, setup_valid_contest, ...):
            # Contest already configured, proceed with test logic
            pass
    """
    mock_repository.get_contest_or_raise.return_value = mock_contest
    return mock_contest


@pytest.fixture
def setup_valid_contest_and_team(mock_repository, mock_contest, mock_contest_team):
    """Pre-configure repository for valid contest and team scenarios.

    Use in tests involving team updates, member operations, etc.
    Skip when testing NotFound error scenarios.

    Args:
        mock_repository: Mock TeamRepository
        mock_contest: Mock Contest object
        mock_contest_team: Mock ContestTeam object

    Returns:
        tuple: (mock_contest, mock_contest_team) for direct access

    Example:
        def test_update(team_service, setup_valid_contest_and_team, ...):
            mock_contest, mock_contest_team = setup_valid_contest_and_team
            # Both contest and team are configured
            pass
    """
    mock_repository.get_contest_or_raise.return_value = mock_contest
    mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
    return mock_contest, mock_contest_team
