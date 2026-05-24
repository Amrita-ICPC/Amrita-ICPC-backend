"""Tests for TeamService.approve_team."""

from unittest.mock import MagicMock, patch

import pytest

from app.schema.team import ContestTeamResponse
from app.utils.enums import TeamApprovalMode, TeamApprovalStatus


class TestApproveTeamSuccess:
    @pytest.mark.asyncio
    async def test_approves_waiting_team_in_instructor_review_contest(
        self,
        team_service,
        mock_repository,
        mock_contest_team_repository,
        mock_contest,
        mock_contest_team,
        mock_contest_team_response,
        contest_id,
        team_id,
        user_id,
    ):
        mock_contest.team_approval_mode = TeamApprovalMode.INSTRUCTOR_REVIEW
        mock_contest_team.approval_status = TeamApprovalStatus.WAITING
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team
        mock_contest_team_repository.update_contest_team.return_value = mock_contest_team

        with patch.object(
            ContestTeamResponse,
            "from_contest_team",
            return_value=mock_contest_team_response,
        ):
            result = await team_service.approve_team(contest_id, team_id, user_id)

        assert result == mock_contest_team_response
        mock_contest_team_repository.update_contest_team.assert_called_once_with(mock_contest_team)

    @pytest.mark.asyncio
    async def test_returns_existing_team_when_already_approved(
        self,
        team_service,
        mock_repository,
        mock_contest_team_repository,
        mock_contest,
        mock_contest_team,
        mock_contest_team_response,
        contest_id,
        team_id,
        user_id,
    ):
        mock_contest.team_approval_mode = TeamApprovalMode.INSTRUCTOR_REVIEW
        mock_contest_team.approval_status = TeamApprovalStatus.APPROVED
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_team_or_raise.return_value = mock_contest_team

        with patch.object(
            ContestTeamResponse,
            "from_contest_team",
            return_value=mock_contest_team_response,
        ):
            result = await team_service.approve_team(contest_id, team_id, user_id)

        assert result == mock_contest_team_response
        mock_contest_team_repository.update_contest_team.assert_not_called()
