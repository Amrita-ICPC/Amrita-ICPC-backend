from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.repositories.student.contest_team import ContestTeamRepository
from app.service.student.student_service import StudentService
from app.utils.enums import (
    ContestTeamMemberStatus,
    TeamStatus,
)


@pytest.fixture
def mock_contest_team_repo():
    return AsyncMock(spec=ContestTeamRepository)


@pytest.fixture
def student_service(mock_contest_team_repo):
    return StudentService(contest_team_repo=mock_contest_team_repo)


@pytest.mark.asyncio
async def test_get_user_invitations_multiple_invitations(
    student_service, mock_contest_team_repo
):
    user_id = uuid4()

    # Mock invitation 1
    invitation1 = MagicMock()
    invitation1.id = uuid4()
    invitation1.status = ContestTeamMemberStatus.INVITED

    invitation1.contest_team.id = uuid4()
    invitation1.contest_team.name = "Team A"
    invitation1.contest_team.team_status = TeamStatus.DRAFT
    invitation1.contest_team.contest_team_member = []

    invitation1.contest_team.contest.id = uuid4()
    invitation1.contest_team.contest.name = "Contest X"
    invitation1.contest_team.contest.description = "Contest X Description"
    invitation1.contest_team.contest.image = "imageX.png"
    invitation1.contest_team.contest.min_team_size = 1
    invitation1.contest_team.contest.max_team_size = 3
    invitation1.contest_team.contest.max_teams = 10

    # Mock invitation 2
    invitation2 = MagicMock()
    invitation2.id = uuid4()
    invitation2.status = ContestTeamMemberStatus.INVITED

    invitation2.contest_team.id = uuid4()
    invitation2.contest_team.name = "Team B"
    invitation2.contest_team.team_status = TeamStatus.DRAFT
    invitation2.contest_team.contest_team_member = []

    invitation2.contest_team.contest.id = uuid4()
    invitation2.contest_team.contest.name = "Contest Y"
    invitation2.contest_team.contest.description = "Contest Y Description"
    invitation2.contest_team.contest.image = "imageY.png"
    invitation2.contest_team.contest.min_team_size = 1
    invitation2.contest_team.contest.max_team_size = 3
    invitation2.contest_team.contest.max_teams = 20

    mock_contest_team_repo.get_contest_team_members_by_user_id.return_value = [
        invitation1,
        invitation2,
    ]
    mock_contest_team_repo.count_teams.return_value = 2
    mock_contest_team_repo.get_active_members_in_contest.return_value = []

    responses = await student_service.get_user_invitations(
        user_id, ContestTeamMemberStatus.INVITED
    )

    assert len(responses) == 2
    assert responses[0].team.name == "Team A"
    assert responses[1].team.name == "Team B"
    assert responses[0].can_accept_invitation is True
    assert responses[1].can_accept_invitation is True

    mock_contest_team_repo.get_contest_team_members_by_user_id.assert_called_once_with(
        user_id=user_id, status=ContestTeamMemberStatus.INVITED
    )


@pytest.mark.asyncio
async def test_get_user_invitations_no_invitations(
    student_service, mock_contest_team_repo
):
    user_id = uuid4()
    mock_contest_team_repo.get_contest_team_members_by_user_id.return_value = []

    responses = await student_service.get_user_invitations(
        user_id, ContestTeamMemberStatus.INVITED
    )

    assert len(responses) == 0
    mock_contest_team_repo.get_contest_team_members_by_user_id.assert_called_once_with(
        user_id=user_id, status=ContestTeamMemberStatus.INVITED
    )
