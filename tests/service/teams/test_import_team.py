import pytest
import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from app.service.student.contest_team import ContestTeamService
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.student.team import StudentTeamRepository
from app.core.guards.team_student import TeamStudentGuard
from app.repositories.contest import ContestRepository
from app.core.guards.contest_student import ContestStudentGuard
from app.models import Contest, ContestTeam, Team, TeamUser
from app.utils.enums import TeamStatus
from app.schema.team import ContestTeamImport
from app.exceptions.team import LeaderMustBeMemberError


@pytest.fixture
def mock_contest_team_repository() -> AsyncMock:
    return AsyncMock(spec=ContestTeamRepository)


@pytest.fixture
def mock_student_team_repository() -> AsyncMock:
    return AsyncMock(spec=StudentTeamRepository)


@pytest.fixture
def mock_team_student_guard() -> AsyncMock:
    return AsyncMock(spec=TeamStudentGuard)


@pytest.fixture
def mock_contest_repository() -> AsyncMock:
    return AsyncMock(spec=ContestRepository)


@pytest.fixture
def mock_contest_student_guard() -> AsyncMock:
    return AsyncMock(spec=ContestStudentGuard)


@pytest.fixture
def contest_team_service(
    mock_contest_team_repository,
    mock_student_team_repository,
    mock_team_student_guard,
    mock_contest_repository,
    mock_contest_student_guard,
) -> ContestTeamService:
    return ContestTeamService(
        repository=mock_contest_team_repository,
        team_repository=mock_student_team_repository,
        team_student_guard=mock_team_student_guard,
        contest_repository=mock_contest_repository,
        contest_student_guard=mock_contest_student_guard,
    )


@pytest.mark.asyncio
async def test_import_team_success(
    contest_team_service,
    mock_contest_repository,
    mock_student_team_repository,
    mock_contest_team_repository,
):
    contest_id = uuid4()
    team_id = uuid4()
    leader_id = uuid4()
    member2_id = uuid4()

    # Mock contest
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.is_public = True
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Mock Team
    mock_team = MagicMock(spec=Team)
    mock_team.id = team_id
    mock_team.name = "My Test Team"
    mock_team.leader_id = leader_id

    # Members on team
    team_user1 = MagicMock(spec=TeamUser)
    team_user1.user_id = leader_id
    team_user2 = MagicMock(spec=TeamUser)
    team_user2.user_id = member2_id
    mock_team.members = [team_user1, team_user2]

    mock_student_team_repository.get_student_team_by_id_or_raise.return_value = mock_team

    # Call import_team
    contest_team_import = ContestTeamImport(
        team_id=team_id,
        member_ids=[leader_id, member2_id],
    )

    # Mock creating return values
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.id = uuid4()
    mock_contest_team_repository.create_contest_team.return_value = mock_contest_team

    await contest_team_service.import_team(
        contest_id=contest_id,
        contest_team_import=contest_team_import,
        user_id=leader_id,
    )

    # Verify calls
    mock_contest_team_repository.create_contest_team.assert_called_once()
    mock_contest_team_repository.create_contest_team_members.assert_called_once()


@pytest.mark.asyncio
async def test_import_team_fails_when_leader_not_in_members(
    contest_team_service,
    mock_contest_repository,
    mock_student_team_repository,
):
    contest_id = uuid4()
    team_id = uuid4()
    leader_id = uuid4()
    member2_id = uuid4()

    # Mock contest
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.is_public = True
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Mock Team
    mock_team = MagicMock(spec=Team)
    mock_team.id = team_id
    mock_team.name = "My Test Team"
    mock_team.leader_id = leader_id

    # Members on team (includes leader and member2)
    team_user1 = MagicMock(spec=TeamUser)
    team_user1.user_id = leader_id
    team_user2 = MagicMock(spec=TeamUser)
    team_user2.user_id = member2_id
    mock_team.members = [team_user1, team_user2]

    mock_student_team_repository.get_student_team_by_id_or_raise.return_value = mock_team

    # Call import_team without the leader in member_ids
    contest_team_import = ContestTeamImport(
        team_id=team_id,
        member_ids=[member2_id],
    )

    with pytest.raises(LeaderMustBeMemberError):
        await contest_team_service.import_team(
            contest_id=contest_id,
            contest_team_import=contest_team_import,
            user_id=leader_id,
        )
