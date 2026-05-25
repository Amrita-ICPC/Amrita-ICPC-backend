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
from app.models import Contest, ContestTeam, ContestTeamMember
from app.utils.enums import TeamStatus, ContestTeamMemberStatus
from app.schema.team import ContestTeamCreate


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
async def test_create_contest_team_success(
    contest_team_service,
    mock_contest_repository,
    mock_contest_team_repository,
):
    contest_id = uuid4()
    user_id = uuid4()

    # Mock contest
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.is_public = True
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Mock return values for create
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.id = uuid4()
    mock_contest_team_repository.create_contest_team.return_value = mock_contest_team

    # Call service method
    contest_team_create = ContestTeamCreate(name="Sparking Devs")
    await contest_team_service.create_contest_team(
        contest_id=contest_id,
        contest_team_create=contest_team_create,
        user_id=user_id,
    )

    # Verify repository calls
    mock_contest_team_repository.create_contest_team.assert_called_once()
    mock_contest_team_repository.create_contest_team_members.assert_called_once()

    # Verify we set status to ACCEPTED for the creator/leader
    args, kwargs = mock_contest_team_repository.create_contest_team_members.call_args
    created_members = args[0]
    assert len(created_members) == 1
    assert created_members[0].user_id == user_id
    assert created_members[0].status == ContestTeamMemberStatus.ACCEPTED


@pytest.mark.asyncio
async def test_create_contest_team_fails_when_max_teams_reached(
    contest_team_service,
    mock_contest_repository,
    mock_contest_team_repository,
):
    from app.exceptions.contest import ContestMaxTeamsReachedError
    contest_id = uuid4()
    user_id = uuid4()

    # Mock contest with max_teams limit
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.is_public = True
    mock_contest.max_teams = 5
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Mock repository to return 5 approved teams
    mock_contest_team_repository.count_teams_by_status.return_value = {
        "approved_count": 5,
        "waiting_count": 0,
        "rejected_count": 0,
        "disqualified_count": 0,
    }

    # Call service method and expect failure
    contest_team_create = ContestTeamCreate(name="Sparking Devs")
    with pytest.raises(ContestMaxTeamsReachedError):
        await contest_team_service.create_contest_team(
            contest_id=contest_id,
            contest_team_create=contest_team_create,
            user_id=user_id,
        )
