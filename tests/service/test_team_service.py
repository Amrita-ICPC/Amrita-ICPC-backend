import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from app.schema.team import TeamCreate, TeamUpdate
from app.exceptions.team import (
    TeamNotFoundError, 
    UserNotFoundError, 
    UserAlreadyInTeamError, 
    UserNotInTeamError
)
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.base import AppBaseException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Models imported to ensure SQLAlchemy mapper registry is populated
from app.models.team import Team, TeamUser
from app.models.user import User
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.service.team_service import TeamService


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def team_service(mock_db):
    # Patch the cache decorators to avoid redis connection issues
    with (
        patch(
            "app.core.cache.decorators.cache_get",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_set",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_delete",
            side_effect=lambda **kwargs: lambda func: func,
        ),
    ):
        from app.service.team_service import TeamService

        service = TeamService(mock_db)
        yield service


@pytest.fixture
def sample_team_data():
    return TeamCreate(
        name="Test Team",
        description="A test team",
        logo="https://example.com/logo.png"
    )


class MockTeam:
    """Mock Team model for testing."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockUser:
    """Mock User model for testing."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockTeamUser:
    """Mock TeamUser model for testing."""
    def __init__(self, team_id, user_id, user=None):
        self.team_id = team_id
        self.user_id = user_id
        self.user = user


@pytest.fixture
def existing_team(sample_team_data):
    team_id = uuid4()
    contest_id = uuid4()
    return MockTeam(
        id=team_id,
        contest_id=contest_id,
        name=sample_team_data.name,
        description=sample_team_data.description,
        logo=sample_team_data.logo,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def existing_user():
    user_id = uuid4()
    return MockUser(
        id=user_id,
        email="test@example.com",
        name="Test User",
        keycloak_id=str(uuid4())
    )


@pytest.fixture
def user_id():
    """Fixture providing a user_id for tests."""
    return uuid4()


# ==================== CREATE TEAM TESTS ====================

@pytest.mark.asyncio
async def test_create_team_success(team_service: "TeamService", mock_db, sample_team_data, existing_team, user_id):
    """Test successful team creation."""
    contest_id = existing_team.contest_id
    
    # Mock contest check and permission check
    def query_side_effect(model):
        mock = MagicMock()
        if model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect
    
    # Mock refresh to update the instance with ID
    def side_effect_refresh(instance):
        instance.id = existing_team.id
        instance.contest_id = contest_id
        instance.created_at = existing_team.created_at
        instance.updated_at = existing_team.updated_at
        return None
    
    mock_db.refresh.side_effect = side_effect_refresh
    
    # Mock permission check
    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        result = await team_service.create_team(sample_team_data, contest_id, user_id)

    assert result.id == existing_team.id
    assert result.name == existing_team.name
    # TeamResponse doesn't expose contest_id in API response
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_once()

@pytest.mark.asyncio
async def test_create_team_contest_not_found(team_service: "TeamService", mock_db, sample_team_data, user_id):
    """Test team creation when contest doesn't exist."""
    contest_id = uuid4()
    
    def query_side_effect(model):
        mock = MagicMock()
        if hasattr(model, '__name__') and model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = None  # Contest not found
        return mock
    
    mock_db.query.side_effect = query_side_effect

    with pytest.raises(ContestNotFoundError):
        await team_service.create_team(sample_team_data, contest_id, user_id)
    
    mock_db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_create_team_integrity_error(team_service: "TeamService", mock_db, sample_team_data, existing_team, user_id):
    """Test team creation with duplicate name."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if hasattr(model, '__name__') and model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()
        return mock
    
    mock_db.query.side_effect = query_side_effect
    mock_db.flush.side_effect = IntegrityError("Duplicate", "", "")

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(AppBaseException) as exc_info:
            await team_service.create_team(sample_team_data, contest_id, user_id)
    
    assert exc_info.value.status_code == 409
    mock_db.rollback.assert_called()


@pytest.mark.asyncio
async def test_create_team_unexpected_error(team_service: "TeamService", mock_db, sample_team_data, existing_team, user_id):
    """Test team creation with unexpected error."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if hasattr(model, '__name__') and model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()
        return mock
    
    mock_db.query.side_effect = query_side_effect
    mock_db.flush.side_effect = RuntimeError("DB Error")

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(AppBaseException):
            await team_service.create_team(sample_team_data, contest_id, user_id)
    
    mock_db.rollback.assert_called_once()


# ==================== GET TEAM BY ID TESTS ====================

@pytest.mark.asyncio
async def test_get_team_by_id_success(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving a team by ID with correct contest validation."""
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = existing_team

    result = await team_service.get_team_by_id(existing_team.id, existing_team.contest_id)

    assert result.id == existing_team.id
    assert result.name == existing_team.name
    # TeamResponse doesn't expose contest_id in API response
    mock_db.query.assert_called_with(Team)


@pytest.mark.asyncio
async def test_get_team_by_id_not_found(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving a non-existent team raises TeamNotFoundError."""
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = None

    with pytest.raises(TeamNotFoundError):
        await team_service.get_team_by_id(uuid4(), existing_team.contest_id)


@pytest.mark.asyncio
async def test_get_team_by_id_wrong_contest(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving team with mismatched contest ID raises TeamNotFoundError."""
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = existing_team
    
    wrong_contest_id = uuid4()

    with pytest.raises(TeamNotFoundError):
        await team_service.get_team_by_id(existing_team.id, wrong_contest_id)


# ==================== GET ALL TEAMS TESTS ====================

@pytest.mark.asyncio
async def test_get_contest_teams_success(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving all teams in a specific contest with pagination."""
    contest_id = existing_team.contest_id
    
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.count.return_value = 1
    mock_filter.offset.return_value.limit.return_value.all.return_value = [existing_team]

    total, teams = await team_service.get_contest_teams(contest_id, skip=0, limit=100)

    assert total == 1
    assert len(teams) == 1
    assert teams[0].id == existing_team.id


@pytest.mark.asyncio
async def test_get_contest_teams_empty(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving teams when none exist in contest."""
    contest_id = existing_team.contest_id
    
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.count.return_value = 0
    mock_filter.offset.return_value.limit.return_value.all.return_value = []

    total, teams = await team_service.get_contest_teams(contest_id, skip=0, limit=100)

    assert total == 0
    assert len(teams) == 0

@pytest.mark.asyncio
async def test_get_contest_teams_pagination(team_service: "TeamService", mock_db, existing_team):
    """Test pagination parameters are applied correctly."""
    contest_id = existing_team.contest_id
    
    team1 = MockTeam(id=uuid4(), contest_id=contest_id, name="Team 1", description="", logo="", 
                     created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    team2 = MockTeam(id=uuid4(), contest_id=contest_id, name="Team 2", description="", logo="",
                     created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.count.return_value = 2
    mock_offset = MagicMock()
    mock_filter.offset.return_value = mock_offset
    mock_offset.limit.return_value.all.return_value = [team1, team2]

    total, teams = await team_service.get_contest_teams(contest_id, skip=10, limit=50)

    assert total == 2
    assert len(teams) == 2
    assert teams[0].name == "Team 1"
    assert teams[1].name == "Team 2"


# ==================== GET USER TEAMS TESTS ====================

@pytest.mark.asyncio
async def test_get_user_teams_success(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test retrieving teams for a specific user in a specific contest."""
    contest_id = existing_team.contest_id
    
    mock_query = mock_db.query.return_value
    mock_query.join.return_value.filter.return_value.filter.return_value.distinct.return_value.count.return_value = 1
    
    distinct_query = mock_db.query.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value
    distinct_query.offset.return_value.limit.return_value.all.return_value = [existing_team]

    total, teams = await team_service.get_user_teams(existing_user.id, contest_id, skip=0, limit=100)

    assert total == 1
    assert len(teams) == 1
    assert teams[0].id == existing_team.id


@pytest.mark.asyncio
async def test_get_user_teams_no_teams(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test user with no teams in a contest returns empty list."""
    contest_id = existing_team.contest_id
    
    mock_query = mock_db.query.return_value
    mock_query.join.return_value.filter.return_value.filter.return_value.distinct.return_value.count.return_value = 0
    
    distinct_query = mock_db.query.return_value.join.return_value.filter.return_value.filter.return_value.distinct.return_value
    distinct_query.offset.return_value.limit.return_value.all.return_value = []

    total, teams = await team_service.get_user_teams(existing_user.id, contest_id, skip=0, limit=100)

    assert total == 0
    assert len(teams) == 0


# ==================== UPDATE TEAM TESTS ====================

@pytest.mark.asyncio
async def test_update_team_success(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test successful team update with contest validation."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect

    update_data = TeamUpdate(name="Updated Team Name")
    
    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        result = await team_service.update_team(existing_team.id, update_data, contest_id, user_id)

    assert result.name == "Updated Team Name"
    assert existing_team.name == "Updated Team Name"
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_with(existing_team)


@pytest.mark.asyncio
async def test_update_team_partial_update(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test partial team update (only description) with contest validation."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect

    update_data = TeamUpdate(description="Updated Description")
    original_name = existing_team.name
    
    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        await team_service.update_team(existing_team.id, update_data, contest_id, user_id)

    assert existing_team.description == "Updated Description"
    assert existing_team.name == original_name  # Should not change
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_team_not_found(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test updating non-existent team."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = None
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect
    update_data = TeamUpdate(name="Updated Team")

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(TeamNotFoundError):
            await team_service.update_team(uuid4(), update_data, contest_id, user_id)


@pytest.mark.asyncio
async def test_update_team_wrong_contest(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test updating team with mismatched contest ID."""
    wrong_contest_id = uuid4()
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect
    update_data = TeamUpdate(name="Updated Team")

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(TeamNotFoundError):
            await team_service.update_team(existing_team.id, update_data, wrong_contest_id, user_id)


@pytest.mark.asyncio
async def test_update_team_database_error(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test update with database error."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect
    mock_db.flush.side_effect = RuntimeError("DB Error")

    update_data = TeamUpdate(name="Updated")

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(AppBaseException):
            await team_service.update_team(existing_team.id, update_data, contest_id, user_id)
    
    mock_db.rollback.assert_called_once()


# ==================== DELETE TEAM TESTS ====================

@pytest.mark.asyncio
async def test_delete_team_success(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test successful team deletion with contest validation."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        else:
            mock.filter.return_value.delete.return_value = None  # TeamUser delete
        return mock
    
    mock_db.query.side_effect = query_side_effect

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        result = await team_service.delete_team(existing_team.id, contest_id, user_id)

    assert result.id == existing_team.id
    mock_db.delete.assert_called_once_with(existing_team)
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_team_not_found(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test deleting non-existent team."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = None
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(TeamNotFoundError):
            await team_service.delete_team(uuid4(), contest_id, user_id)


@pytest.mark.asyncio
async def test_delete_team_wrong_contest(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test deleting team with mismatched contest ID."""
    wrong_contest_id = uuid4()
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        return mock
    
    mock_db.query.side_effect = query_side_effect

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(TeamNotFoundError):
            await team_service.delete_team(existing_team.id, wrong_contest_id, user_id)


@pytest.mark.asyncio
async def test_delete_team_database_error(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test delete with database error."""
    contest_id = existing_team.contest_id
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        elif model.__name__ == 'Contest':
            mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
        else:
            mock.filter.return_value.delete.return_value = None  # TeamUser delete
        return mock
    
    mock_db.query.side_effect = query_side_effect
    mock_db.flush.side_effect = RuntimeError("DB Error")

    with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
        with pytest.raises(AppBaseException):
            await team_service.delete_team(existing_team.id, contest_id, user_id)
    
    mock_db.rollback.assert_called_once()


# ==================== ADD MEMBER TO TEAM TESTS ====================

@pytest.mark.asyncio
async def test_add_member_to_team_success(team_service: "TeamService", mock_db, existing_team, existing_user, user_id):
    """Test successfully adding a member to team with contest validation."""
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = None  # User not yet in team
            elif model.__name__ == 'Contest':
                mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            result = await team_service.add_member_to_team(existing_team.id, existing_user.id, contest_id, user_id)

        assert result.user_id == existing_user.id
        assert result.team_id == existing_team.id
        assert result.message == "Member added successfully"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_add_member_team_not_found(team_service: "TeamService", existing_user, existing_team, user_id):
    """Test adding member to non-existent team."""
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', side_effect=TeamNotFoundError(str(existing_team.id))):
        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            with pytest.raises(TeamNotFoundError):
                await team_service.add_member_to_team(existing_team.id, existing_user.id, contest_id, user_id)


@pytest.mark.asyncio
async def test_add_member_user_not_found(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test adding non-existent user to team."""
    team_member_id = uuid4()
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = None
            elif model.__name__ == 'Contest':
                mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            with pytest.raises(UserNotFoundError):
                await team_service.add_member_to_team(existing_team.id, team_member_id, contest_id, user_id)


@pytest.mark.asyncio
async def test_add_member_already_in_team(team_service: "TeamService", mock_db, existing_team, existing_user, user_id):
    """Test adding user who's already in the team."""
    contest_id = existing_team.contest_id
    team_user = MockTeamUser(existing_team.id, existing_user.id)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = team_user  # Already exists
            elif model.__name__ == 'Contest':
                mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            with pytest.raises(UserAlreadyInTeamError):
                await team_service.add_member_to_team(existing_team.id, existing_user.id, contest_id, user_id)


# ==================== REMOVE MEMBER FROM TEAM TESTS ====================

@pytest.mark.asyncio
async def test_remove_member_from_team_success(team_service: "TeamService", mock_db, existing_team, existing_user, user_id):
    """Test successfully removing a member from team with contest validation."""
    contest_id = existing_team.contest_id
    team_user = MockTeamUser(existing_team.id, existing_user.id)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = team_user
            elif model.__name__ == 'Contest':
                mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            result = await team_service.remove_member_from_team(existing_team.id, existing_user.id, contest_id, user_id)

        assert result.user_id == existing_user.id
        assert result.team_id == existing_team.id
        assert result.message == "Member removed successfully"
        mock_db.delete.assert_called_once_with(team_user)
        mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_remove_member_team_not_found(team_service: "TeamService", existing_user, existing_team, user_id):
    """Test removing member from non-existent team."""
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', side_effect=TeamNotFoundError(str(existing_team.id))):
        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            with pytest.raises(TeamNotFoundError):
                await team_service.remove_member_from_team(existing_team.id, existing_user.id, contest_id, user_id)


@pytest.mark.asyncio
async def test_remove_member_user_not_found(team_service: "TeamService", mock_db, existing_team, user_id):
    """Test removing non-existent user from team with contest validation."""
    team_member_id = uuid4()
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = None
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = None
            elif model.__name__ == 'Contest':
                mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            with pytest.raises(UserNotFoundError):
                await team_service.remove_member_from_team(existing_team.id, team_member_id, contest_id, user_id)


@pytest.mark.asyncio
async def test_remove_member_not_in_team(team_service: "TeamService", mock_db, existing_team, existing_user, user_id):
    """Test removing user who's not in the team with contest validation."""
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = None  # Not in team
            elif model.__name__ == 'Contest':
                mock.filter.return_value.first.return_value = MagicMock()  # Contest exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with patch('app.core.permissions.ContestPermission.can_manage_contest', return_value=True):
            with pytest.raises(UserNotInTeamError):
                await team_service.remove_member_from_team(existing_team.id, existing_user.id, contest_id, user_id)


# ==================== GET TEAM MEMBERS TESTS ====================

@pytest.mark.asyncio
async def test_get_team_members_success(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test retrieving all members of a team with contest validation."""
    contest_id = existing_team.contest_id
    team_user = MockTeamUser(existing_team.id, existing_user.id, user=existing_user)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        mock_query = mock_db.query.return_value
        mock_query.options.return_value.filter.return_value.all.return_value = [team_user]

        result = await team_service.get_team_members(existing_team.id, contest_id)

        assert len(result) == 1
        assert result[0].id == existing_user.id
        assert result[0].email == existing_user.email


@pytest.mark.asyncio
async def test_get_team_members_empty(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving members for team with no members."""
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        mock_query = mock_db.query.return_value
        mock_query.options.return_value.filter.return_value.all.return_value = []

        result = await team_service.get_team_members(existing_team.id, contest_id)

        assert len(result) == 0


@pytest.mark.asyncio
async def test_get_team_members_team_not_found(team_service: "TeamService", existing_team):
    """Test getting members for non-existent team."""
    contest_id = existing_team.contest_id
    
    with patch.object(team_service, 'get_team_by_id', side_effect=TeamNotFoundError(str(existing_team.id))):
        with pytest.raises(TeamNotFoundError):
            await team_service.get_team_members(existing_team.id, contest_id)


@pytest.mark.asyncio
async def test_get_team_members_multiple(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving multiple members of a team with contest validation."""
    contest_id = existing_team.contest_id
    user1 = MockUser(id=uuid4(), email="user1@example.com", name="User 1", keycloak_id=str(uuid4()))
    user2 = MockUser(id=uuid4(), email="user2@example.com", name="User 2", keycloak_id=str(uuid4()))
    
    team_user1 = MockTeamUser(existing_team.id, user1.id, user=user1)
    team_user2 = MockTeamUser(existing_team.id, user2.id, user=user2)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        mock_query = mock_db.query.return_value
        mock_query.options.return_value.filter.return_value.all.return_value = [team_user1, team_user2]

        result = await team_service.get_team_members(existing_team.id, contest_id)

        assert len(result) == 2
        assert result[0].id == user1.id
        assert result[1].id == user2.id
