import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import InvalidTeamSizeError, TeamAlreadyExistsError
from app.models.contest import Contest, ContestTeam
from app.models.team import Team
from app.models.user import User
from app.schema.team import TeamCreate
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
    def query_side_effect(model):
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
            # Query for existing participation: .join(...).filter(...).first()
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q

        if model == ContestTeam:
            # Query for existing participation: .join(...).filter(...).first()
            q = MagicMock()
            q.join.return_value.filter.return_value.first.return_value = None
            return q

        if model == User:
            # Query for user validation: .filter(...).first()
            q = MagicMock()
            q.filter.return_value.first.return_value = MagicMock(spec=User)
            return q

        return MagicMock()

        return MagicMock()

    mock_db.query.side_effect = query_side_effect

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
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
            q = MagicMock()
            q.filter.return_value.first.return_value = MagicMock(spec=User)
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
            q = MagicMock()
            q.filter.return_value.first.return_value = MagicMock(spec=User)
            return q
        return MagicMock()  # Fallback

    mock_db.query.side_effect = query_side_effect

    # Mock TeamPermission to raise PermissionDeniedError
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.core.permissions.ContestPermission.can_manage_contest",
            lambda *args, **kwargs: None,
        )

        def mock_is_student_allowed(db, user_id, contest_id):
            if user_id == member_id:
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
