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
from app.models import Contest, ContestTeam, ContestTeamMember, Team
from app.utils.enums import ContestTeamMemberStatus, TeamStatus
from app.exceptions.student.teams import (
    TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException,
    InvalidContestTeamMemberStatusUpdateException,
)
from app.exceptions.team import InvalidTeamSizeError, CannotRemoveTeamLeaderError
from app.exceptions.contest import InvalidContestError, StudentAlreadyInContestError


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
async def test_update_status_success(contest_team_service, mock_contest_repository, mock_contest_team_repository):
    user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    # Mock contest with valid registration dates
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 5
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Mock contest team in DRAFT status
    mock_team = MagicMock(spec=Team)
    mock_team.name = "Awesome Team"
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.team = mock_team
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Mock count of team members
    mock_contest_team_repository.count_contest_team_members.return_value = 2

    # Mock contest team member
    mock_member = MagicMock(spec=ContestTeamMember)
    mock_member.user_id = user_id
    mock_member.status = ContestTeamMemberStatus.INVITED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    # Call service method to accept
    await contest_team_service.update_contest_team_member_status(
        user_id=user_id,
        contest_id=contest_id,
        contest_team_id=contest_team_id,
        contest_team_member_id=member_id,
        contest_team_member_status=ContestTeamMemberStatus.ACCEPTED,
    )

    # Assertions
    assert mock_member.status == ContestTeamMemberStatus.ACCEPTED
    mock_contest_team_repository.update_contest_team_member.assert_called_once_with(mock_member)


@pytest.mark.asyncio
async def test_update_status_raises_invalid_status_transition(contest_team_service, mock_contest_repository, mock_contest_team_repository):
    user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    mock_contest = MagicMock(spec=Contest)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Member is already LEFT
    mock_member = MagicMock(spec=ContestTeamMember)
    mock_member.user_id = user_id
    mock_member.status = ContestTeamMemberStatus.LEFT
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    with pytest.raises(InvalidContestTeamMemberStatusUpdateException):
        await contest_team_service.update_contest_team_member_status(
            user_id=user_id,
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=member_id,
            contest_team_member_status=ContestTeamMemberStatus.ACCEPTED,
        )


@pytest.mark.asyncio
async def test_update_status_raises_registration_time_error(contest_team_service, mock_contest_repository, mock_contest_team_repository):
    user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    # Registration in the future
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now + datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=2)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    mock_member = MagicMock(spec=ContestTeamMember)
    mock_member.user_id = user_id
    mock_member.status = ContestTeamMemberStatus.INVITED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    with pytest.raises(InvalidContestError):
        await contest_team_service.update_contest_team_member_status(
            user_id=user_id,
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=member_id,
            contest_team_member_status=ContestTeamMemberStatus.ACCEPTED,
        )


@pytest.mark.asyncio
async def test_update_status_raises_team_status_not_allowed(contest_team_service, mock_contest_repository, mock_contest_team_repository):
    user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    # Valid registration window
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 2
    mock_contest.max_team_size = 5
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Team is already CONFIRMED
    mock_team = MagicMock(spec=Team)
    mock_team.name = "My Team"
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.CONFIRMED
    mock_contest_team.team = mock_team
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    mock_member = MagicMock(spec=ContestTeamMember)
    mock_member.user_id = user_id
    mock_member.status = ContestTeamMemberStatus.INVITED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    with pytest.raises(TeamStatusNotAllowedForUpdatingContestTeamMemberStatusException):
        await contest_team_service.update_contest_team_member_status(
            user_id=user_id,
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=member_id,
            contest_team_member_status=ContestTeamMemberStatus.ACCEPTED,
        )


@pytest.mark.asyncio
async def test_update_status_raises_invalid_team_size(contest_team_service, mock_contest_repository, mock_contest_team_repository):
    user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    # Valid registration window, max team size = 2
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest.min_team_size = 1
    mock_contest.max_team_size = 2
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Team in draft
    mock_team = MagicMock(spec=Team)
    mock_team.name = "Full Team"
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.team = mock_team
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Already has 2 accepted members
    mock_contest_team_repository.count_contest_team_members.return_value = 2

    mock_member = MagicMock(spec=ContestTeamMember)
    mock_member.user_id = user_id
    mock_member.status = ContestTeamMemberStatus.INVITED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    with pytest.raises(InvalidTeamSizeError):
        await contest_team_service.update_contest_team_member_status(
            user_id=user_id,
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=member_id,
            contest_team_member_status=ContestTeamMemberStatus.ACCEPTED,
        )


@pytest.mark.asyncio
async def test_leader_cannot_remove_himself(contest_team_service, mock_contest_repository, mock_contest_team_repository):
    leader_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    # Valid registration window
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    mock_team = MagicMock(spec=Team)
    mock_team.name = "Lead Team"
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.team = mock_team
    mock_contest_team.leader_id = leader_id
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    mock_member = MagicMock(spec=ContestTeamMember)
    # The member being removed is the leader
    mock_member.user_id = leader_id
    mock_member.status = ContestTeamMemberStatus.ACCEPTED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    with pytest.raises(CannotRemoveTeamLeaderError):
        await contest_team_service.update_contest_team_member_status(
            user_id=leader_id,
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=member_id,
            contest_team_member_status=ContestTeamMemberStatus.REMOVED,
        )


@pytest.mark.asyncio
async def test_leader_leaving_with_other_members_promotes_new_leader(
    contest_team_service, mock_contest_repository, mock_contest_team_repository
):
    leader_id = uuid4()
    other_user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    leader_member_id = uuid4()

    # Valid registration window
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Team in draft
    mock_team = MagicMock(spec=Team)
    mock_team.name = "Byte Force"
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.team = mock_team
    mock_contest_team.leader_id = leader_id
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Mock leader member
    leader_member = MagicMock(spec=ContestTeamMember)
    leader_member.user_id = leader_id
    leader_member.status = ContestTeamMemberStatus.ACCEPTED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = leader_member

    # Mock other member who has accepted
    other_member = MagicMock(spec=ContestTeamMember)
    other_member.user_id = other_user_id
    other_member.status = ContestTeamMemberStatus.ACCEPTED
    other_member.confirmed_at = now - datetime.timedelta(hours=1)

    # Mock get_contest_team_members returning both
    mock_contest_team_repository.get_contest_team_members.return_value = [leader_member, other_member]

    # Call service to leave
    await contest_team_service.update_contest_team_member_status(
        user_id=leader_id,
        contest_id=contest_id,
        contest_team_id=contest_team_id,
        contest_team_member_id=leader_member_id,
        contest_team_member_status=ContestTeamMemberStatus.LEFT,
    )

    # Assertions: leadership was transferred to the other member, status updated to LEFT
    assert mock_contest_team.leader_id == other_user_id
    assert leader_member.status == ContestTeamMemberStatus.LEFT
    mock_contest_team_repository.update_contest_team.assert_called_once_with(mock_contest_team)
    mock_contest_team_repository.update_contest_team_member.assert_called_once_with(leader_member)


@pytest.mark.asyncio
async def test_leader_leaving_last_cancels_team(
    contest_team_service, mock_contest_repository, mock_contest_team_repository
):
    leader_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    leader_member_id = uuid4()

    # Valid registration window
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Team in draft
    mock_team = MagicMock(spec=Team)
    mock_team.name = "Byte Force"
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team.team = mock_team
    mock_contest_team.leader_id = leader_id
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    # Mock leader member
    leader_member = MagicMock(spec=ContestTeamMember)
    leader_member.user_id = leader_id
    leader_member.status = ContestTeamMemberStatus.ACCEPTED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = leader_member

    # Mock get_contest_team_members returning only the leader
    mock_contest_team_repository.get_contest_team_members.return_value = [leader_member]

    # Call service to leave
    await contest_team_service.update_contest_team_member_status(
        user_id=leader_id,
        contest_id=contest_id,
        contest_team_id=contest_team_id,
        contest_team_member_id=leader_member_id,
        contest_team_member_status=ContestTeamMemberStatus.LEFT,
    )

    # Assertions: team is cancelled, leader_id set to None, status updated to LEFT
    assert mock_contest_team.team_status == TeamStatus.CANCELLED
    assert mock_contest_team.leader_id is None
    assert leader_member.status == ContestTeamMemberStatus.LEFT
    mock_contest_team_repository.update_contest_team.assert_called_once_with(mock_contest_team)
    mock_contest_team_repository.update_contest_team_member.assert_called_once_with(leader_member)
    mock_contest_team_repository.update_contest_team_members_status.assert_called_once_with(
        contest_team_id=mock_contest_team.id,
        from_statuses=[ContestTeamMemberStatus.INVITED, ContestTeamMemberStatus.ACCEPTED],
        to_status=ContestTeamMemberStatus.CANCELLED,
        exclude_user_id=leader_id,
    )


@pytest.mark.asyncio
async def test_accept_raises_if_already_in_contest(
    contest_team_service,
    mock_contest_repository,
    mock_contest_team_repository,
    mock_contest_student_guard,
):
    user_id = uuid4()
    contest_id = uuid4()
    contest_team_id = uuid4()
    member_id = uuid4()

    # Valid registration window
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_contest = MagicMock(spec=Contest)
    mock_contest.registration_start = now - datetime.timedelta(days=1)
    mock_contest.registration_end = now + datetime.timedelta(days=1)
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest

    # Team in draft
    mock_contest_team = MagicMock(spec=ContestTeam)
    mock_contest_team.team_status = TeamStatus.DRAFT
    mock_contest_team_repository.get_contest_team_by_id_or_raise.return_value = mock_contest_team

    mock_member = MagicMock(spec=ContestTeamMember)
    mock_member.user_id = user_id
    mock_member.status = ContestTeamMemberStatus.INVITED
    mock_contest_team_repository.get_contest_team_member_or_raise.return_value = mock_member

    # Mock the guard to raise StudentAlreadyInContestError
    mock_contest_student_guard.check_student_already_in_contest.side_effect = StudentAlreadyInContestError(
        user_id=str(user_id), contest_id=str(contest_id)
    )

    with pytest.raises(StudentAlreadyInContestError):
        await contest_team_service.update_contest_team_member_status(
            user_id=user_id,
            contest_id=contest_id,
            contest_team_id=contest_team_id,
            contest_team_member_id=member_id,
            contest_team_member_status=ContestTeamMemberStatus.ACCEPTED,
        )


