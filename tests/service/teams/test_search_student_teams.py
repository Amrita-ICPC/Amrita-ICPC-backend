import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.guards.team_student import TeamStudentGuard
from app.models.team import Team
from app.repositories.dto.pagination import PaginatedResult, PaginationParams
from app.repositories.student.team import StudentTeamRepository
from app.repositories.user import UserRepository
from app.schema.student.teams import StudentTeamListResponse, StudentTeamCardResponse
from app.service.student.team import StudentTeamService
from app.utils.enums import InvitationType, TeamInvitationStatus

# Disable caching decorators globally for tests
patch("app.core.cache.decorators.cache_get", lambda **kw: lambda f: f).start()
patch("app.core.cache.decorators.cache_set", lambda **kw: lambda f: f).start()
patch("app.core.cache.decorators.cache_delete", lambda **kw: lambda f: f).start()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock StudentTeamRepository."""
    mock = AsyncMock(spec=StudentTeamRepository)
    mock.search_teams_by_name = AsyncMock()
    mock.get_pending_student_invitations_count = AsyncMock()
    mock.get_team_by_code = AsyncMock()
    mock.create_student_team = AsyncMock()
    mock.get_user_pending_join_requests_data = AsyncMock()
    mock.get_student_team_invitations = AsyncMock()
    return mock


@pytest.fixture
def mock_user_repository() -> AsyncMock:
    """Mock UserRepository."""
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def mock_guard() -> MagicMock:
    """Mock TeamStudentGuard."""
    return MagicMock(spec=TeamStudentGuard)


@pytest.fixture
def student_team_service(
    mock_repository: AsyncMock,
    mock_user_repository: AsyncMock,
    mock_guard: MagicMock,
) -> StudentTeamService:
    """StudentTeamService with mocked dependencies."""
    return StudentTeamService(
        repository=mock_repository,
        user_repository=mock_user_repository,
        guard=mock_guard,
    )


@pytest.mark.asyncio
async def test_search_teams_by_name_success(
    student_team_service: StudentTeamService,
    mock_repository: AsyncMock,
):
    """Test that search_teams_by_name delegates successfully to repository and maps result."""
    user_id = uuid.uuid4()
    name_query = "CodeQuest"
    pagination = PaginationParams(skip=0, limit=10)

    # Mock domain Team objects
    mock_team_1 = MagicMock(spec=Team)
    mock_team_1.id = uuid.uuid4()
    mock_team_1.name = "CodeQuest Elite"
    mock_team_1.description = "Elite competitive programming team"
    mock_team_1.logo = "https://example.com/logo1.png"
    mock_team_1.created_at = __import__("datetime").datetime.now()
    mock_team_1.updated_at = __import__("datetime").datetime.now()
    mock_team_1.leader_id = user_id
    mock_team_1.members = []  # No members in mock list
    mock_team_1.is_public = True
    mock_team_1.code = "123456"

    mock_team_2 = MagicMock(spec=Team)
    mock_team_2.id = uuid.uuid4()
    mock_team_2.name = "CodeQuest Beginners"
    mock_team_2.description = "Beginner friendly team"
    mock_team_2.logo = None
    mock_team_2.created_at = __import__("datetime").datetime.now()
    mock_team_2.updated_at = __import__("datetime").datetime.now()
    mock_team_2.leader_id = uuid.uuid4()
    mock_team_2.members = []
    mock_team_2.is_public = False
    mock_team_2.code = "654321"

    # Configure mock repository responses
    mock_repository.search_teams_by_name.return_value = PaginatedResult(
        total=2,
        items=[mock_team_1, mock_team_2],
    )
    mock_repository.get_pending_student_invitations_count.return_value = 5
    mock_repository.get_user_pending_join_requests_data.return_value = ({mock_team_1.id}, 3)

    # Run the service method
    result: StudentTeamListResponse = await student_team_service.search_teams_by_name(
        name=name_query,
        pagination=pagination,
        user_id=user_id,
    )

    # Verifications
    mock_repository.search_teams_by_name.assert_called_once_with(
        name_query=name_query,
        pagination=pagination,
    )
    mock_repository.get_pending_student_invitations_count.assert_called_once_with(
        user_id=user_id,
        invitation_type=InvitationType.INVITE,
        team_id=None,
    )
    mock_repository.get_user_pending_join_requests_data.assert_called_once_with(user_id)

    # Check mapping correctness
    assert result.total == 2
    assert len(result.teams) == 2
    assert result.pending_invitation_count == 5
    assert result.pending_request_count == 3

    # Verify first team mapping
    assert result.teams[0].id == mock_team_1.id
    assert result.teams[0].title == "CodeQuest Elite"
    assert result.teams[0].is_public is True
    assert result.teams[0].code == "123456"
    assert result.teams[0].has_requested is True

    # Verify second team mapping
    assert result.teams[1].id == mock_team_2.id
    assert result.teams[1].title == "CodeQuest Beginners"
    assert result.teams[1].is_public is False
    assert result.teams[1].code == "654321"
    assert result.teams[1].has_requested is False


@pytest.mark.asyncio
async def test_create_student_team_success(
    student_team_service: StudentTeamService,
    mock_repository: AsyncMock,
):
    """Test that create_student_team successfully generates a 6-digit random code, handles creation, and maps the result."""
    user_id = uuid.uuid4()
    team_name = "Dynamic Coders"
    team_description = "A dynamic team"

    # Return None for get_team_by_code to signify candidate code is unique
    mock_repository.get_team_by_code.return_value = None

    def capture_team_creation(team_obj: Team):
        # Dynamically populate id, created_at, updated_at to mock DB behavior
        team_obj.id = uuid.uuid4()
        team_obj.created_at = __import__("datetime").datetime.now()
        team_obj.updated_at = __import__("datetime").datetime.now()
        team_obj.members = []
        return team_obj

    mock_repository.create_student_team.side_effect = capture_team_creation

    # Run the service method
    result: StudentTeamCardResponse = await student_team_service.create_student_team(
        user_id=user_id,
        team_name=team_name,
        team_description=team_description,
        is_public=False,
    )

    # Verifications
    assert mock_repository.get_team_by_code.called
    assert mock_repository.create_student_team.called

    # Fetch the actual Team object passed to the repository mock
    created_team = mock_repository.create_student_team.call_args[0][0]
    assert created_team.name == team_name
    assert created_team.description == team_description
    assert created_team.leader_id == user_id
    assert created_team.is_public is False
    assert len(created_team.code) == 6
    assert created_team.code.isdigit()

    # Verify return mappings
    assert result.title == team_name
    assert result.description == team_description
    assert result.is_leader is True
    assert result.is_public is False
    assert result.code == created_team.code
    assert result.has_requested is False


@pytest.mark.asyncio
async def test_get_team_invitations_with_sent_filtering(
    student_team_service: StudentTeamService,
    mock_repository: AsyncMock,
):
    """Test get_team_invitations with sent parameter enabled."""
    user_id = uuid.uuid4()
    mock_repository.get_student_team_invitations.return_value = []

    # Run the service method with sent=True
    result = await student_team_service.get_team_invitations(
        user_id=user_id,
        invitation_type=InvitationType.REQUEST,
        invitation_status=TeamInvitationStatus.PENDING,
        team_id=None,
        sent=True,
    )

    # Verifications
    mock_repository.get_student_team_invitations.assert_called_once_with(
        user_id=user_id,
        invitation_type=InvitationType.REQUEST,
        invitation_status=TeamInvitationStatus.PENDING,
        team_id=None,
        sent=True,
    )
    assert result.total == 0
    assert len(result.invitations) == 0
