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
    with patch("app.core.cache.decorators.cache_get", side_effect=lambda **_kwargs: lambda func: func), \
         patch("app.core.cache.decorators.cache_set", side_effect=lambda **_kwargs: lambda func: func), \
         patch("app.core.cache.decorators.cache_delete", side_effect=lambda **_kwargs: lambda func: func):

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
    return MockTeam(
        id=team_id,
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


# ==================== CREATE TEAM TESTS ====================

@pytest.mark.asyncio
async def test_create_team_success(team_service: "TeamService", mock_db, sample_team_data, existing_team):
    """Test successful team creation."""
    
    # Mock refresh to update the instance with ID
    def side_effect_refresh(instance):
        instance.id = existing_team.id
        instance.created_at = existing_team.created_at
        instance.updated_at = existing_team.updated_at
        return None
    
    mock_db.refresh.side_effect = side_effect_refresh

    result = await team_service.create_team(sample_team_data)

    assert result.id == existing_team.id
    assert result.name == existing_team.name
    assert result.description == existing_team.description
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_create_team_integrity_error(team_service: "TeamService", mock_db, sample_team_data):
    """Test team creation with duplicate name."""
    mock_db.add.side_effect = IntegrityError("Duplicate", "", "")
    mock_db.flush.side_effect = IntegrityError("Duplicate", "", "")

    with pytest.raises(AppBaseException) as exc_info:
        await team_service.create_team(sample_team_data)
    
    assert exc_info.value.status_code == 409
    mock_db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_create_team_unexpected_error(team_service: "TeamService", mock_db, sample_team_data):
    """Test team creation with unexpected error."""
    mock_db.flush.side_effect = RuntimeError("DB Error")

    with pytest.raises(AppBaseException):
        await team_service.create_team(sample_team_data)
    
    mock_db.rollback.assert_called_once()


# ==================== GET TEAM BY ID TESTS ====================

@pytest.mark.asyncio
async def test_get_team_by_id_success(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving a team by ID successfully."""
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = existing_team

    result = await team_service.get_team_by_id(existing_team.id)

    assert result.id == existing_team.id
    assert result.name == existing_team.name
    mock_db.query.assert_called_with(Team)


@pytest.mark.asyncio
async def test_get_team_by_id_not_found(team_service: "TeamService", mock_db):
    """Test retrieving a non-existent team raises TeamNotFoundError."""
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = None
    team_id = uuid4()

    with pytest.raises(TeamNotFoundError):
        await team_service.get_team_by_id(team_id)


# ==================== GET ALL TEAMS TESTS ====================

@pytest.mark.asyncio
async def test_get_all_teams_success(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving all teams with pagination."""
    mock_query = mock_db.query.return_value
    mock_query.count.return_value = 1
    mock_query.offset.return_value.limit.return_value.all.return_value = [existing_team]

    total, teams = await team_service.get_all_teams(skip=0, limit=100)

    assert total == 1
    assert len(teams) == 1
    assert teams[0].id == existing_team.id
    mock_db.query.assert_called_with(Team)


@pytest.mark.asyncio
async def test_get_all_teams_empty(team_service: "TeamService", mock_db):
    """Test retrieving all teams when none exist."""
    mock_query = mock_db.query.return_value
    mock_query.count.return_value = 0
    mock_query.offset.return_value.limit.return_value.all.return_value = []

    total, teams = await team_service.get_all_teams(skip=0, limit=100)

    assert total == 0
    assert len(teams) == 0


@pytest.mark.asyncio
async def test_get_all_teams_pagination(team_service: "TeamService", mock_db):
    """Test pagination parameters are applied correctly."""
    team1 = MockTeam(id=uuid4(), name="Team 1", description="", logo="", 
                     created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    team2 = MockTeam(id=uuid4(), name="Team 2", description="", logo="",
                     created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    
    mock_query = mock_db.query.return_value
    mock_query.count.return_value = 2
    mock_offset = MagicMock()
    mock_query.offset.return_value = mock_offset
    mock_offset.limit.return_value.all.return_value = [team1, team2]

    total, teams = await team_service.get_all_teams(skip=10, limit=50)

    assert total == 2
    assert len(teams) == 2
    mock_query.offset.assert_called_with(10)
    mock_offset.limit.assert_called_with(50)


# ==================== GET USER TEAMS TESTS ====================

@pytest.mark.asyncio
async def test_get_user_teams_success(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test retrieving teams for a specific user."""
    mock_query = mock_db.query.return_value
    mock_query.join.return_value.filter.return_value.distinct.return_value.count.return_value = 1
    
    distinct_query = mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value
    distinct_query.offset.return_value.limit.return_value.all.return_value = [existing_team]

    total, teams = await team_service.get_user_teams(existing_user.id, skip=0, limit=100)

    assert total == 1
    assert len(teams) == 1
    assert teams[0].id == existing_team.id


@pytest.mark.asyncio
async def test_get_user_teams_no_teams(team_service: "TeamService", mock_db, existing_user):
    """Test user with no teams returns empty list."""
    mock_query = mock_db.query.return_value
    mock_query.join.return_value.filter.return_value.distinct.return_value.count.return_value = 0
    
    distinct_query = mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value
    distinct_query.offset.return_value.limit.return_value.all.return_value = []

    total, teams = await team_service.get_user_teams(existing_user.id, skip=0, limit=100)

    assert total == 0
    assert len(teams) == 0


# ==================== UPDATE TEAM TESTS ====================

@pytest.mark.asyncio
async def test_update_team_success(team_service: "TeamService", mock_db, existing_team):
    """Test successful team update."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        return mock
    
    mock_db.query.side_effect = query_side_effect

    update_data = TeamUpdate(name="Updated Team Name")
    
    result = await team_service.update_team(existing_team.id, update_data)

    assert result.name == "Updated Team Name"
    assert existing_team.name == "Updated Team Name"
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_with(existing_team)


@pytest.mark.asyncio
async def test_update_team_partial_update(team_service: "TeamService", mock_db, existing_team):
    """Test partial team update (only description)."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        return mock
    
    mock_db.query.side_effect = query_side_effect

    update_data = TeamUpdate(description="Updated Description")
    original_name = existing_team.name
    
    await team_service.update_team(existing_team.id, update_data)

    assert existing_team.description == "Updated Description"
    assert existing_team.name == original_name  # Should not change
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_team_not_found(team_service: "TeamService", mock_db):
    """Test updating non-existent team."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = None
        return mock
    
    mock_db.query.side_effect = query_side_effect
    team_id = uuid4()
    update_data = TeamUpdate(name="Updated Team")

    with pytest.raises(TeamNotFoundError):
        await team_service.update_team(team_id, update_data)


@pytest.mark.asyncio
async def test_update_team_database_error(team_service: "TeamService", mock_db, existing_team):
    """Test update with database error."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        return mock
    
    mock_db.query.side_effect = query_side_effect
    mock_db.flush.side_effect = RuntimeError("DB Error")

    update_data = TeamUpdate(name="Updated")

    with pytest.raises(AppBaseException):
        await team_service.update_team(existing_team.id, update_data)
    
    mock_db.rollback.assert_called_once()


# ==================== DELETE TEAM TESTS ====================

@pytest.mark.asyncio
async def test_delete_team_success(team_service: "TeamService", mock_db, existing_team):
    """Test successful team deletion."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        return mock
    
    mock_db.query.side_effect = query_side_effect

    result = await team_service.delete_team(existing_team.id)

    assert result.id == existing_team.id
    mock_db.delete.assert_called_once_with(existing_team)
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_team_not_found(team_service: "TeamService", mock_db):
    """Test deleting non-existent team."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = None
        return mock
    
    mock_db.query.side_effect = query_side_effect
    team_id = uuid4()

    with pytest.raises(TeamNotFoundError):
        await team_service.delete_team(team_id)


@pytest.mark.asyncio
async def test_delete_team_database_error(team_service: "TeamService", mock_db, existing_team):
    """Test delete with database error."""
    def query_side_effect(model):
        mock = MagicMock()
        if model == Team:
            mock.filter.return_value.first.return_value = existing_team
        return mock
    
    mock_db.query.side_effect = query_side_effect
    mock_db.flush.side_effect = RuntimeError("DB Error")

    with pytest.raises(AppBaseException):
        await team_service.delete_team(existing_team.id)
    
    mock_db.rollback.assert_called_once()


# ==================== ADD MEMBER TO TEAM TESTS ====================

@pytest.mark.asyncio
async def test_add_member_to_team_success(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test successfully adding a member to team."""
    # Mock get_team_by_id
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        # Mock user query
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = None  # User not yet in team
            return mock
        
        mock_db.query.side_effect = query_side_effect

        result = await team_service.add_member_to_team(existing_team.id, existing_user.id)

        assert result.user_id == existing_user.id
        assert result.team_id == existing_team.id
        assert result.message == "Member added successfully"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_add_member_team_not_found(team_service: "TeamService", existing_user):
    """Test adding member to non-existent team."""
    team_id = uuid4()
    
    with patch.object(team_service, 'get_team_by_id', side_effect=TeamNotFoundError(str(team_id))):
        with pytest.raises(TeamNotFoundError):
            await team_service.add_member_to_team(team_id, existing_user.id)


@pytest.mark.asyncio
async def test_add_member_user_not_found(team_service: "TeamService", mock_db, existing_team):
    """Test adding non-existent user to team."""
    user_id = uuid4()
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = None
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with pytest.raises(UserNotFoundError):
            await team_service.add_member_to_team(existing_team.id, user_id)


@pytest.mark.asyncio
async def test_add_member_already_in_team(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test adding user who's already in the team."""
    team_user = MockTeamUser(existing_team.id, existing_user.id)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = team_user  # Already exists
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with pytest.raises(UserAlreadyInTeamError):
            await team_service.add_member_to_team(existing_team.id, existing_user.id)


# ==================== REMOVE MEMBER FROM TEAM TESTS ====================

@pytest.mark.asyncio
async def test_remove_member_from_team_success(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test successfully removing a member from team."""
    team_user = MockTeamUser(existing_team.id, existing_user.id)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = team_user
            return mock
        
        mock_db.query.side_effect = query_side_effect

        result = await team_service.remove_member_from_team(existing_team.id, existing_user.id)

        assert result.user_id == existing_user.id
        assert result.team_id == existing_team.id
        assert result.message == "Member removed succesfully"
        mock_db.delete.assert_called_once_with(team_user)
        mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_remove_member_team_not_found(team_service: "TeamService", existing_user):
    """Test removing member from non-existent team."""
    team_id = uuid4()
    
    with patch.object(team_service, 'get_team_by_id', side_effect=TeamNotFoundError(str(team_id))):
        with pytest.raises(TeamNotFoundError):
            await team_service.remove_member_from_team(team_id, existing_user.id)


@pytest.mark.asyncio
async def test_remove_member_user_not_found(team_service: "TeamService", mock_db, existing_team):
    """Test removing non-existent user from team."""
    user_id = uuid4()
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = None
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with pytest.raises(UserNotFoundError):
            await team_service.remove_member_from_team(existing_team.id, user_id)


@pytest.mark.asyncio
async def test_remove_member_not_in_team(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test removing user who's not in the team."""
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        def query_side_effect(model):
            mock = MagicMock()
            if model == User:
                mock.filter.return_value.first.return_value = existing_user
            elif model == TeamUser:
                mock.filter.return_value.first.return_value = None  # Not in team
            return mock
        
        mock_db.query.side_effect = query_side_effect

        with pytest.raises(UserNotInTeamError):
            await team_service.remove_member_from_team(existing_team.id, existing_user.id)


# ==================== GET TEAM MEMBERS TESTS ====================

@pytest.mark.asyncio
async def test_get_team_members_success(team_service: "TeamService", mock_db, existing_team, existing_user):
    """Test retrieving all members of a team."""
    team_user = MockTeamUser(existing_team.id, existing_user.id, user=existing_user)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        mock_query = mock_db.query.return_value
        mock_query.options.return_value.filter.return_value.all.return_value = [team_user]

        result = await team_service.get_team_members(existing_team.id)

        assert len(result) == 1
        assert result[0].id == existing_user.id
        assert result[0].email == existing_user.email


@pytest.mark.asyncio
async def test_get_team_members_empty(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving members for team with no members."""
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        mock_query = mock_db.query.return_value
        mock_query.options.return_value.filter.return_value.all.return_value = []

        result = await team_service.get_team_members(existing_team.id)

        assert len(result) == 0


@pytest.mark.asyncio
async def test_get_team_members_team_not_found(team_service: "TeamService"):
    """Test getting members for non-existent team."""
    team_id = uuid4()
    
    with patch.object(team_service, 'get_team_by_id', side_effect=TeamNotFoundError(str(team_id))):
        with pytest.raises(TeamNotFoundError):
            await team_service.get_team_members(team_id)


@pytest.mark.asyncio
async def test_get_team_members_multiple(team_service: "TeamService", mock_db, existing_team):
    """Test retrieving multiple members of a team."""
    user1 = MockUser(id=uuid4(), email="user1@example.com", name="User 1", keycloak_id=str(uuid4()))
    user2 = MockUser(id=uuid4(), email="user2@example.com", name="User 2", keycloak_id=str(uuid4()))
    
    team_user1 = MockTeamUser(existing_team.id, user1.id, user=user1)
    team_user2 = MockTeamUser(existing_team.id, user2.id, user=user2)
    
    with patch.object(team_service, 'get_team_by_id', return_value=existing_team):
        mock_query = mock_db.query.return_value
        mock_query.options.return_value.filter.return_value.all.return_value = [team_user1, team_user2]

        result = await team_service.get_team_members(existing_team.id)

        assert len(result) == 2
        assert result[0].id == user1.id
        assert result[1].id == user2.id
