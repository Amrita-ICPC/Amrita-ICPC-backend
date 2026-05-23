import pytest
import datetime
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock

from app.service.student.contest_team import ContestTeamService
from app.repositories.student.contest_team import ContestTeamRepository
from app.repositories.student.team import StudentTeamRepository
from app.core.guards.team_student import TeamStudentGuard
from app.repositories.contest import ContestRepository
from app.core.guards.contest_student import ContestStudentGuard
from app.models import Contest, ContestTeam, ContestTeamMember, Team, User
from app.utils.enums import ContestTeamMemberStatus, TeamStatus
from app.exceptions.student.teams import (
    TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException,
)
from app.exceptions.team import (
    InvalidTeamSizeError,
    MemberAlreadyInTeamError,
    TeamMemberAccessDeniedError,
    StudentTeamNotFoundError,
)
from app.exceptions.contest import (
    StudentAlreadyInContestError,
    ContestTeamNotFoundException,
    InvalidContestError,
)

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
def mock_contest_student_guard() -> MagicMock:
    return MagicMock(spec=ContestStudentGuard)


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
async def test_invite_members_success_public_contest_no_underlying_team(
    contest_team_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_team_student_guard,
):
    contest_id = uuid4()
    team_id = uuid4()
    contest_team_id = uuid4()
    leader_id = uuid4()
    invitee_id = uuid4()

    # Mock public contest with valid registration dates
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 3
    mock_contest.is_public = True
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Mock contest team in DRAFT status, no underlying team_id
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.contest_id = contest_id
    mock_contest_team.team_id = None
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.name = "My Contest Team"
    mock_contest_team.leader_id = leader_id
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Mock count of team members (only the leader)
    mock_contest_team_repository.count_contest_team_members.return_value = 1
    # Mock current members check (none of the invitees are in team yet)
    mock_contest_team_repository.get_contest_team_members.return_value = []

    # Mock active members in contest query - return empty list
    mock_contest_team_repository.get_active_members_in_contest.return_value = []

    # Call service
    await contest_team_service.invite_members(
        contest_id=contest_id,
        team_id=team_id,
        contest_team_id=contest_team_id,
        invite_user_ids=[invitee_id],
        user_id=leader_id,
    )

    # Asserts
    mock_team_student_guard.check_is_contest_team_leader.assert_called_once_with(
        user_id=leader_id, contest_team=mock_contest_team
    )
    mock_contest_team_repository.create_contest_team_members.assert_called_once()
    args = mock_contest_team_repository.create_contest_team_members.call_args[0][0]
    assert len(args) == 1
    assert args[0].user_id == invitee_id
    assert args[0].status == ContestTeamMemberStatus.INVITED


@pytest.mark.asyncio
async def test_invite_members_invalid_registration_dates(
    contest_team_service, mock_contest_repository
):
    contest_id = uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now + datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=2)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    with pytest.raises(InvalidContestError):
        await contest_team_service.invite_members(
            contest_id=contest_id,
            team_id=uuid4(),
            contest_team_id=uuid4(),
            invite_user_ids=[uuid4()],
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_invite_members_not_draft_team(
    contest_team_service, mock_contest_repository, mock_contest_team_repository
):
    contest_id = uuid4()
    team_id = uuid4()
    contest_team_id = uuid4()

    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.contest_id = contest_id
    mock_contest_team.team_id = team_id
    mock_contest_team.team_status = TeamStatus.CONFIRMED
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    with pytest.raises(TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException):
        await contest_team_service.invite_members(
            contest_id=contest_id,
            team_id=team_id,
            contest_team_id=contest_team_id,
            invite_user_ids=[uuid4()],
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_invite_members_exceeds_capacity(
    contest_team_service, mock_contest_repository, mock_contest_team_repository
):
    contest_id = uuid4()
    team_id = uuid4()
    contest_team_id = uuid4()

    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 2
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.contest_id = contest_id
    mock_contest_team.team_id = team_id
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Mock 2 active members count (already at capacity limit)
    mock_contest_team_repository.count_contest_team_members.return_value = 2

    with pytest.raises(InvalidTeamSizeError):
        await contest_team_service.invite_members(
            contest_id=contest_id,
            team_id=team_id,
            contest_team_id=contest_team_id,
            invite_user_ids=[uuid4()],
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_invite_members_already_in_team(
    contest_team_service, mock_contest_repository, mock_contest_team_repository
):
    contest_id = uuid4()
    team_id = uuid4()
    contest_team_id = uuid4()
    invitee_id = uuid4()

    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 5
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.contest_id = contest_id
    mock_contest_team.team_id = team_id
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.name = "My Team"
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Mock count of team members
    mock_contest_team_repository.count_contest_team_members.return_value = 1
    # Mock invitee already in team with status INVITED
    m1 = MagicMock(spec=ContestTeamMember)
    m1.user_id = invitee_id
    m1.status = ContestTeamMemberStatus.INVITED
    mock_contest_team_repository.get_contest_team_members.return_value = [m1]

    with pytest.raises(MemberAlreadyInTeamError):
        await contest_team_service.invite_members(
            contest_id=contest_id,
            team_id=team_id,
            contest_team_id=contest_team_id,
            invite_user_ids=[invitee_id],
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_invite_members_already_active_in_contest(
    contest_team_service, mock_contest_repository, mock_contest_team_repository
):
    contest_id = uuid4()
    team_id = uuid4()
    contest_team_id = uuid4()
    invitee_id = uuid4()

    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 5
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.contest_id = contest_id
    mock_contest_team.team_id = team_id
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team
    mock_contest_team_repository.count_contest_team_members.return_value = 1
    mock_contest_team_repository.get_contest_team_members.return_value = []

    # Mock invitee active in another team in this contest
    active_member = MagicMock(spec=ContestTeamMember)
    active_member.user_id = invitee_id
    mock_contest_team_repository.get_active_members_in_contest.return_value = [active_member]

    with pytest.raises(StudentAlreadyInContestError):
        await contest_team_service.invite_members(
            contest_id=contest_id,
            team_id=team_id,
            contest_team_id=contest_team_id,
            invite_user_ids=[invitee_id],
            user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_invite_members_not_in_underlying_team(
    contest_team_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_student_team_repository,
):
    contest_id = uuid4()
    team_id = uuid4()
    contest_team_id = uuid4()
    invitee_id = uuid4()

    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 5
    mock_contest.is_public = True
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.contest_id = contest_id
    mock_contest_team.team_id = team_id
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.name = "My Team"
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team
    mock_contest_team_repository.count_contest_team_members.return_value = 1
    mock_contest_team_repository.get_contest_team_members.return_value = []
    mock_contest_team_repository.get_active_members_in_contest.return_value = []

    # Mock underlying team members - invitee is NOT in the list
    other_member = MagicMock(spec=User)
    other_member.id = uuid4()
    mock_student_team_repository.get_team_members.return_value = [
        (other_member, None, None, None)
    ]

    with pytest.raises(TeamMemberAccessDeniedError):
        await contest_team_service.invite_members(
            contest_id=contest_id,
            team_id=team_id,
            contest_team_id=contest_team_id,
            invite_user_ids=[invitee_id],
            user_id=uuid4(),
        )
