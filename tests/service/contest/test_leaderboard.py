"""Tests for ContestService.get_contest_leaderboard."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.models.contest import (
    ContestTeam,
)
from app.schema.leaderboard import LeaderboardResponse
from app.utils.enums import ContestStatus


class TestGetContestLeaderboard:
    """Test suite for contest leaderboard standings calculation."""

    @pytest.mark.asyncio
    async def test_get_contest_leaderboard_not_found(
        self,
        contest_service,
        mock_contest_repository,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        contest_id = uuid4()
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.get_contest_leaderboard(contest_id, user_id)

    @pytest.mark.asyncio
    async def test_get_contest_leaderboard_deleted(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest is soft-deleted."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.status = ContestStatus.DELETED

        with pytest.raises(ContestNotFoundError):
            await contest_service.get_contest_leaderboard(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_get_contest_leaderboard_permission_denied(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.status = ContestStatus.PUBLISHED
        mock_guard.check_read_contest.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.get_contest_leaderboard(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_get_contest_leaderboard_success(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        """Test successful calculation of leaderboard standings."""
        # 1. Setup contest details
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.status = ContestStatus.PUBLISHED

        # 2. Setup mock Teams
        t1_id = uuid4()
        t2_id = uuid4()

        team1 = MagicMock(spec=ContestTeam)
        team1.id = t1_id
        team1.name = "Team 1"

        team2 = MagicMock(spec=ContestTeam)
        team2.id = t2_id
        team2.name = "Team 2"

        # Mock repository to return ranked teams directly along with total count
        mock_contest_repository.get_teams_ranked_by_score.return_value = (
            [(team1, 115), (team2, 50)],
            2,
        )

        # 3. Call service method
        response, total = await contest_service.get_contest_leaderboard(
            mock_contest.id, user_id
        )

        # 4. Verify result
        assert isinstance(response, LeaderboardResponse)
        assert response.contest_id == mock_contest.id
        assert len(response.standings) == 2
        assert total == 2

        # Team 1 assertions (Rank 1, Score 115)
        t1_row = response.standings[0]
        assert t1_row.rank == 1
        assert t1_row.team_id == t1_id
        assert t1_row.team_name == "Team 1"
        assert t1_row.total_score == 115
        assert not hasattr(t1_row, "question_details")

        # Team 2 assertions (Rank 2, Score 50)
        t2_row = response.standings[1]
        assert t2_row.rank == 2
        assert t2_row.team_id == t2_id
        assert t2_row.team_name == "Team 2"
        assert t2_row.total_score == 50
        assert not hasattr(t2_row, "question_details")

        # Verify calls
        mock_contest_repository.get_contest_or_raise.assert_called_once_with(
            mock_contest.id
        )
        mock_guard.check_read_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )
        mock_contest_repository.get_teams_ranked_by_score.assert_called_once_with(
            mock_contest.id,
            search_term=None,
            sort_order="desc",
            skip=0,
            limit=50,
        )
