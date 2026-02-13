import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import InvalidTeamSizeError, TeamAlreadyExistsError
from app.models.contest import Contest, ContestTeam
from app.models.team import Team
from app.models.user import User
from app.schema.team import ContestTeamResponse, TeamCreate
from app.service.team_service import TeamService
from app.utils.enums import TeamStatus


@pytest.fixture
def mock_db():
    mock = MagicMock(spec=Session)

    def refresh_side_effect(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    mock.refresh.side_effect = refresh_side_effect
    return mock


@pytest.fixture
def team_service(mock_db):
    return TeamService(mock_db)


@pytest.fixture(autouse=True)
def disable_cache():
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.core.config.config.CACHE_ENABLED", False)
        yield


@pytest.mark.asyncio
async def test_create_team_success(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()
    member_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest.id = contest_id
    mock_contest.max_team_size = 3
    mock_contest.min_team_size = 1

    # Robust mocking for query chains
    query_call_count = 0

    def query_side_effect(model):
        nonlocal query_call_count

        if model == Contest:
            # Query for contest: .filter(...).first()
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q

        if model == Team:
            # Query for existing team check: .join(...).filter(...).first()
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q

        if model == ContestTeam:
            query_call_count += 1

            if query_call_count <= 2:
                # First two queries are permission checks - should return None
                q = MagicMock()
                q.join.return_value.filter.return_value.first.return_value = None
                return q
            else:
                # Final query gets the created contest team with relationship
                team_id = uuid.uuid4()

                # Create a mock that behaves like a real object for Pydantic
                mock_team = SimpleNamespace(
                    id=team_id,
                    name="Test Team",
                    description="Description",
                    logo=None,
                    leader_id=member_id,
                    created_by=instructor_id,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                mock_contest_team = SimpleNamespace(
                    team=mock_team, team_status=TeamStatus.DRAFT
                )

                q = MagicMock()
                options_mock = MagicMock()
                filter_mock = MagicMock()

                # directly assign the final result
                filter_mock.first.return_value = mock_contest_team
                options_mock.filter.return_value = filter_mock
                q.options.return_value = options_mock
                return q

        if model == User:
            # Create mock user for both individual and bulk queries
            mock_user = MagicMock(spec=User)
            mock_user.id = member_id
            mock_user.name = "Test User"
            mock_user.email = "test@example.com"

            q = MagicMock()
            # Handle .filter(...).first() for individual user lookup
            q.filter.return_value.first.return_value = mock_user
            # Handle .filter(User.id.in_(...)).all() for bulk user validation
            q.filter.return_value.all.return_value = [mock_user]
            return q

        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )
        # Mock TeamPermission validation
        m.setattr(
            "app.core.permissions.TeamPermission.is_student_allowed_for_contest",
            lambda *args, **kwargs: None,
        )

        # Mock the ContestTeamResponse.from_contest_team to prevent Pydantic validation issues
        expected_response = ContestTeamResponse(
            id=uuid.uuid4(),
            name="Test Team",
            description="Description",
            logo=None,
            status=TeamStatus.DRAFT,
            leader_id=member_id,
            created_by=instructor_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        m.setattr(
            "app.schema.team.ContestTeamResponse.from_contest_team",
            lambda *args, **kwargs: expected_response,
        )

        team_data = TeamCreate(
            name="Test Team",
            description="Description",
            member_ids=[member_id],
            leader_id=member_id,
            status=TeamStatus.DRAFT,
        )

        response = await team_service.create_team(contest_id, team_data, instructor_id)

        assert response.name == "Test Team"
        assert mock_db.add.call_count >= 1


@pytest.mark.asyncio
async def test_create_team_contest_not_found(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()

    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    team_data = TeamCreate(name="Test Team")

    with pytest.raises(ContestNotFoundError):
        await team_service.create_team(contest_id, team_data, instructor_id)


@pytest.mark.asyncio
async def test_create_team_already_exists(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest.id = contest_id

    mock_team = MagicMock(spec=Team)

    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == Team:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = mock_team
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )

        team_data = TeamCreate(name="Existing Team")

        with pytest.raises(TeamAlreadyExistsError):
            await team_service.create_team(contest_id, team_data, instructor_id)


@pytest.mark.asyncio
async def test_create_team_invalid_size_max(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()
    member_id_1 = uuid.uuid4()
    member_id_2 = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest.max_team_size = 1

    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == Team:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )

        team_data = TeamCreate(
            name="Team",
            member_ids=[member_id_1, member_id_2],
            leader_id=member_id_1,
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.create_team(contest_id, team_data, instructor_id)


@pytest.mark.asyncio
async def test_create_team_invalid_size_min_confirmed(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest.max_team_size = 3
    mock_contest.min_team_size = 2

    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == Team:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q
        if model == ContestTeam:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )

        member_id = uuid.uuid4()
        team_data = TeamCreate(
            name="Team",
            member_ids=[member_id],
            leader_id=member_id,
            status=TeamStatus.CONFIRMED,
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.create_team(contest_id, team_data, instructor_id)


@pytest.mark.asyncio
async def test_create_team_valid_size_min_draft(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()
    member_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest.max_team_size = 3
    mock_contest.min_team_size = 2

    query_call_count = 0

    def query_side_effect(model):
        nonlocal query_call_count

        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == Team:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q
        if model == ContestTeam:
            query_call_count += 1

            if query_call_count <= 2:
                # First two queries are permission checks - should return None
                q = MagicMock()
                q.join.return_value.filter.return_value.first.return_value = None
                return q
            else:
                # Final query gets the created contest team with relationship
                team_id = uuid.uuid4()

                # Create a mock that behaves like a real object for Pydantic
                mock_team = SimpleNamespace(
                    id=team_id,
                    name="Team",
                    description=None,
                    logo=None,
                    leader_id=member_id,
                    created_by=instructor_id,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

                mock_contest_team = SimpleNamespace(
                    team=mock_team, team_status=TeamStatus.DRAFT
                )

                q = MagicMock()
                options_mock = MagicMock()
                filter_mock = MagicMock()

                # directly assign the final result
                filter_mock.first.return_value = mock_contest_team
                options_mock.filter.return_value = filter_mock
                q.options.return_value = options_mock
                return q
        if model == User:
            # Create mock user for both individual and bulk queries
            mock_user = MagicMock(spec=User)
            mock_user.id = member_id
            mock_user.name = "Test User"
            mock_user.email = "test@example.com"

            q = MagicMock()
            # Handle .filter(...).first() for individual user lookup
            q.filter.return_value.first.return_value = mock_user
            # Handle .filter(User.id.in_(...)).all() for bulk user validation
            q.filter.return_value.all.return_value = [mock_user]
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )
        # Mock TeamPermission validation
        m.setattr(
            "app.core.permissions.TeamPermission.is_student_allowed_for_contest",
            lambda *args, **kwargs: None,
        )

        # Mock the ContestTeamResponse.from_contest_team to prevent Pydantic validation issues
        expected_response = ContestTeamResponse(
            id=uuid.uuid4(),
            name="Team",
            description=None,
            logo=None,
            status=TeamStatus.DRAFT,
            leader_id=member_id,
            created_by=instructor_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        m.setattr(
            "app.schema.team.ContestTeamResponse.from_contest_team",
            lambda *args, **kwargs: expected_response,
        )

        team_data = TeamCreate(
            name="Team",
            member_ids=[member_id],
            leader_id=member_id,
            status=TeamStatus.DRAFT,
        )

        response = await team_service.create_team(contest_id, team_data, instructor_id)
        assert response.name == "Team"


@pytest.mark.asyncio
async def test_create_team_user_already_in_contest(team_service, mock_db):
    contest_id = uuid.uuid4()
    instructor_id = uuid.uuid4()
    member_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest.max_team_size = 3
    mock_contest.min_team_size = 1

    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == Team:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q
        if model == ContestTeam:
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q
        if model == User:
            # Create mock user for both individual and bulk queries
            mock_user = MagicMock(spec=User)
            mock_user.id = member_id
            mock_user.name = "Test User"
            mock_user.email = "test@example.com"

            q = MagicMock()
            # Handle .filter(...).first() for individual user lookup
            q.filter.return_value.first.return_value = mock_user
            # Handle .filter(User.id.in_(...)).all() for bulk user validation
            q.filter.return_value.all.return_value = [mock_user]
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    # Mock TeamPermission to raise PermissionDeniedError
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )

        def mock_is_student_allowed(*args, **kwargs):
            raise PermissionDeniedError("User already in team")

        m.setattr(
            "app.core.permissions.TeamPermission.is_student_allowed_for_contest",
            mock_is_student_allowed,
        )

        team_data = TeamCreate(
            name="Team",
            member_ids=[member_id],
            leader_id=member_id,
            status=TeamStatus.DRAFT,
        )

        with pytest.raises(PermissionDeniedError):
            await team_service.create_team(contest_id, team_data, instructor_id)


@pytest.mark.asyncio
async def test_get_contest_teams(team_service, mock_db):
    """Test retrieving teams for a contest with filtering."""
    contest_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Mock contest query for permission check
    mock_contest = MagicMock(spec=Contest)

    # Mock query chain
    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == ContestTeam:
            q = MagicMock()
            # Create the query chain: options().join().filter()
            options_chain = q.options.return_value
            join_chain = options_chain.join.return_value
            filter_chain = join_chain.filter.return_value

            # Ensure count() returns actual integer, not MagicMock
            filter_chain.count.return_value = 2

            # Mock results
            mock_team1 = MagicMock(spec=Team)
            mock_team1.id = uuid.uuid4()
            mock_team1.name = "Team A"
            mock_team1.description = "Description A"
            mock_team1.logo = None
            mock_team1.leader_id = uuid.uuid4()
            mock_team1.created_by = uuid.uuid4()
            mock_team1.created_at = datetime.now()
            mock_team1.updated_at = datetime.now()
            mock_team1.members = []

            mock_ct1 = MagicMock(spec=ContestTeam)
            mock_ct1.team = mock_team1
            mock_ct1.team_status = TeamStatus.CONFIRMED

            mock_team2 = MagicMock(spec=Team)
            mock_team2.id = uuid.uuid4()
            mock_team2.name = "Team B"
            mock_team2.description = None
            mock_team2.logo = "http://logo.com"
            mock_team2.leader_id = None
            mock_team2.created_by = uuid.uuid4()
            mock_team2.created_at = datetime.now()
            mock_team2.updated_at = datetime.now()
            mock_team2.members = []

            mock_ct2 = MagicMock(spec=ContestTeam)
            mock_ct2.team = mock_team2
            mock_ct2.team_status = TeamStatus.DRAFT

            filter_chain.offset.return_value.limit.return_value.all.return_value = [
                mock_ct1,
                mock_ct2,
            ]
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    # Mock permission check
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_read_contest",
            lambda *args, **kwargs: None,
        )

        # Test without filters
        total, teams = await team_service.get_contest_teams(contest_id, user_id)

        assert total == 2
        assert len(teams) == 2
        assert teams[0].name == "Team A"
        assert teams[1].name == "Team B"

        # Test with search
        await team_service.get_contest_teams(contest_id, user_id, search_term="Team A")

        # Test with status
        await team_service.get_contest_teams(
            contest_id, user_id, status=TeamStatus.CONFIRMED
        )


@pytest.mark.asyncio
async def test_get_team_by_id_success(team_service, mock_db):
    """Test retrieving a specific team by ID."""
    contest_id = uuid.uuid4()
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)

    mock_team = MagicMock(spec=Team)
    mock_team.id = team_id
    mock_team.name = "My Team"
    mock_team.description = "Desc"
    mock_team.logo = None
    mock_team.leader_id = uuid.uuid4()
    mock_team.created_by = uuid.uuid4()
    mock_team.created_at = datetime.now()
    mock_team.updated_at = datetime.now()
    mock_team.members = []

    mock_ct = MagicMock(spec=ContestTeam)
    mock_ct.team = mock_team
    mock_ct.team_status = TeamStatus.CONFIRMED

    # Mock query
    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == ContestTeam:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_ct
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    # Mock permission check
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_read_contest",
            lambda *args, **kwargs: None,
        )

        result = await team_service.get_team_by_id(contest_id, team_id, user_id)

        assert result.id == team_id
        assert result.name == "My Team"
        assert result.status == TeamStatus.CONFIRMED


@pytest.mark.asyncio
async def test_get_team_by_id_not_found(team_service, mock_db):
    """Test retrieving a non-existent team raises TeamNotFoundError."""
    contest_id = uuid.uuid4()
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)

    # Mock queries
    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        if model == ContestTeam:
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    # Mock permission check
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_read_contest",
            lambda *args, **kwargs: None,
        )

        from app.exceptions.team import TeamNotFoundError

        with pytest.raises(TeamNotFoundError):
            await team_service.get_team_by_id(contest_id, team_id, user_id)


@pytest.mark.asyncio
async def test_get_contest_teams_permission_denied(team_service, mock_db):
    """Test retrieving teams raises PermissionDeniedError if access denied."""
    contest_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_contest = MagicMock(spec=Contest)

    def query_side_effect(model):
        if model == Contest:
            q = MagicMock()
            q.filter.return_value.first.return_value = mock_contest
            return q
        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    # Mock permission check to raise error
    with pytest.MonkeyPatch.context() as m:

        def mock_can_read(*args, **kwargs):
            raise PermissionDeniedError("Denied")

        m.setattr(
            "app.core.permissions.ContestPermission.can_read_contest",
            mock_can_read,
        )

        with pytest.raises(PermissionDeniedError):
            await team_service.get_contest_teams(contest_id, user_id)
