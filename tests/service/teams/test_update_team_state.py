from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.service.team_service import TeamService
from app.utils.enums import TeamApprovalMode, TeamApprovalStatus, TeamStatus




@pytest.fixture
def contest_id():
    return uuid4()


@pytest.fixture
def team_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def mock_contest():
    contest = MagicMock()
    contest.id = uuid4()
    return contest


@pytest.fixture
def mock_contest_team():
    ct = MagicMock()
    ct.contest_id = uuid4()
    ct.team_id = uuid4()
    ct.team_status = TeamStatus.DRAFT
    ct.approval_status = TeamApprovalStatus.WAITING
    return ct


@pytest.mark.asyncio
class TestUpdateTeamState:
    async def test_reject_team_success(
        self,
        team_service: TeamService,
        mock_repository: MagicMock,
        mock_guard: MagicMock,
        mock_contest: MagicMock,
        mock_contest_team: MagicMock,
        contest_id: UUID,
        team_id: UUID,
        user_id: UUID,
    ):
        mock_contest.team_approval_mode = TeamApprovalMode.INSTRUCTOR_REVIEW
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.update_team_approval_status.return_value = mock_contest_team

        with patch("app.service.team_service.to_contest_team_response"):
            await team_service.reject_team(contest_id, team_id, user_id)

            mock_guard.check_update_team.assert_called_once_with(
                user_id=user_id, contest=mock_contest
            )
            mock_repository.update_team_approval_status.assert_called_once_with(
                mock_contest_team, TeamApprovalStatus.REJECTED
            )

    async def test_confirm_team_success(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        mock_contest_team,
        contest_id,
        team_id,
        user_id,
    ):
        mock_contest.team_approval_mode = TeamApprovalMode.INSTRUCTOR_REVIEW
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.update_team_status.return_value = mock_contest_team

        with patch("app.service.team_service.to_contest_team_response"):
            await team_service.confirm_team(contest_id, team_id, user_id)

            mock_guard.check_update_team.assert_called_once_with(
                user_id=user_id, contest=mock_contest
            )
            mock_repository.update_team_status.assert_called_once_with(
                mock_contest_team, TeamStatus.CONFIRMED
            )

    async def test_confirm_team_auto_approve_success(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        mock_contest_team,
        contest_id,
        team_id,
        user_id,
    ):
        mock_contest.team_approval_mode = TeamApprovalMode.AUTO_APPROVE
        mock_contest_team.approval_status = TeamApprovalStatus.WAITING
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.update_team_status.return_value = mock_contest_team

        with patch("app.service.team_service.to_contest_team_response"):
            await team_service.confirm_team(contest_id, team_id, user_id)

            assert mock_contest_team.approval_status == TeamApprovalStatus.APPROVED
            mock_guard.check_update_team.assert_called_once_with(
                user_id=user_id, contest=mock_contest
            )
            mock_repository.update_team_status.assert_called_once_with(
                mock_contest_team, TeamStatus.CONFIRMED
            )

    async def test_disqualify_team_success(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        mock_contest_team,
        contest_id,
        team_id,
        user_id,
    ):
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_repository.update_team_status.return_value = mock_contest_team

        with patch("app.service.team_service.to_contest_team_response"):
            await team_service.disqualify_team(contest_id, team_id, user_id)

            mock_guard.check_update_team.assert_called_once_with(
                user_id=user_id, contest=mock_contest
            )
            mock_repository.update_team_status.assert_called_once_with(
                mock_contest_team, TeamStatus.DISQUALIFIED
            )
