"""Tests for ContestService.get_contest_leaderboard."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.models.contest import (
    ContestSubmission,
    ContestTeam,
    ContestTeamMember,
)
from app.models.question import Question, Submission
from app.schema.leaderboard import LeaderboardResponse
from app.utils.enums import ContestStatus, ContestTeamMemberStatus, SubmissionStatus


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
        start_time = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
        mock_contest.start_time = start_time

        # 2. Setup mock Questions
        q_a_id = uuid4()
        q_b_id = uuid4()

        q_a = MagicMock(spec=Question)
        q_a.id = q_a_id
        q_a.title = "Question A"

        q_b = MagicMock(spec=Question)
        q_b.id = q_b_id
        q_b.title = "Question B"

        questions = [q_a, q_b]

        # 3. Setup mock Teams and Members
        t1_id = uuid4()
        t2_id = uuid4()

        # Team 1 accepted members
        m11_id = uuid4()
        m11 = MagicMock(spec=ContestTeamMember)
        m11.id = m11_id
        m11.status = ContestTeamMemberStatus.ACCEPTED

        m12_id = uuid4()
        m12 = MagicMock(spec=ContestTeamMember)
        m12.id = m12_id
        m12.status = ContestTeamMemberStatus.ACCEPTED

        team1 = MagicMock(spec=ContestTeam)
        team1.id = t1_id
        team1.name = "Team 1"
        team1.contest_team_member = [m11, m12]

        # Team 2 accepted & pending members
        m21_id = uuid4()
        m21 = MagicMock(spec=ContestTeamMember)
        m21.id = m21_id
        m21.status = ContestTeamMemberStatus.ACCEPTED

        m22_id = uuid4()
        m22 = MagicMock(spec=ContestTeamMember)
        m22.id = m22_id
        m22.status = ContestTeamMemberStatus.INVITED

        team2 = MagicMock(spec=ContestTeam)
        team2.id = t2_id
        team2.name = "Team 2"
        team2.contest_team_member = [m21, m22]

        teams = [team1, team2]

        # Helper function to create submission mock
        def create_submission(
            sub_id,
            team_id,
            member_id,
            question_id,
            score,
            is_evaluated,
            status,
            created_at,
        ):
            sub = MagicMock(spec=Submission)
            sub.id = sub_id
            sub.question_id = question_id
            sub.score = score
            sub.is_evaluated = is_evaluated
            sub.status = status
            sub.created_at = created_at

            cs = MagicMock(spec=ContestSubmission)
            cs.contest_team_id = team_id
            cs.contest_team_member_id = member_id
            sub.contest_submission = cs
            return sub

        # 4. Setup mock Submissions
        submissions = [
            # Team 1, Member 1.1 submissions
            create_submission(
                uuid4(),
                t1_id,
                m11_id,
                q_a_id,
                80.0,
                True,
                SubmissionStatus.AC,
                datetime(2026, 6, 17, 12, 10, 0, tzinfo=timezone.utc),
            ),
            create_submission(
                uuid4(),
                t1_id,
                m11_id,
                q_a_id,
                100.0,
                True,
                SubmissionStatus.AC,
                datetime(2026, 6, 17, 12, 15, 0, tzinfo=timezone.utc),
            ),
            create_submission(
                uuid4(),
                t1_id,
                m11_id,
                q_b_id,
                40.0,
                True,
                SubmissionStatus.WA,
                datetime(2026, 6, 17, 12, 20, 0, tzinfo=timezone.utc),
            ),
            # Team 1, Member 1.2 submissions
            create_submission(
                uuid4(),
                t1_id,
                m12_id,
                q_a_id,
                90.0,
                True,
                SubmissionStatus.AC,
                datetime(2026, 6, 17, 12, 5, 0, tzinfo=timezone.utc),
            ),
            # Team 2, Member 2.1 submissions
            create_submission(
                uuid4(),
                t2_id,
                m21_id,
                q_a_id,
                50.0,
                True,
                SubmissionStatus.AC,
                datetime(2026, 6, 17, 12, 30, 0, tzinfo=timezone.utc),
            ),
            create_submission(
                uuid4(),
                t2_id,
                m21_id,
                q_b_id,
                70.0,
                False,
                SubmissionStatus.AC,
                datetime(2026, 6, 17, 12, 35, 0, tzinfo=timezone.utc),
            ),  # not evaluated
            # Team 2, Member 2.2 (Pending member) submission (should be ignored in member best score but counts in attempts/solved)
            create_submission(
                uuid4(),
                t2_id,
                m22_id,
                q_a_id,
                100.0,
                True,
                SubmissionStatus.AC,
                datetime(2026, 6, 17, 12, 5, 0, tzinfo=timezone.utc),
            ),
        ]

        mock_contest_repository.get_contest_leaderboard_raw_data.return_value = (
            teams,
            questions,
            submissions,
        )

        # 5. Call service method
        response = await contest_service.get_contest_leaderboard(
            mock_contest.id, user_id
        )

        # 6. Verify result
        assert isinstance(response, LeaderboardResponse)
        assert response.contest_id == mock_contest.id
        assert len(response.standings) == 2

        # Team 1 assertions (Rank 1, Score 115)
        t1_row = response.standings[0]
        assert t1_row.rank == 1
        assert t1_row.team_id == t1_id
        assert t1_row.team_name == "Team 1"
        assert t1_row.total_score == 115
        assert len(t1_row.question_details) == 2

        # Question A for Team 1: Avg of 100 and 90 = 95
        q_a_detail_t1 = next(
            q for q in t1_row.question_details if q.question_id == q_a_id
        )
        assert q_a_detail_t1.question_title == "Question A"
        assert q_a_detail_t1.score == 95
        assert q_a_detail_t1.is_solved is True
        assert q_a_detail_t1.attempts == 3
        assert (
            q_a_detail_t1.time_taken_seconds == 300
        )  # min AC at 12:05 (5 mins = 300s)

        # Question B for Team 1: Avg of 40 and 0 = 20
        q_b_detail_t1 = next(
            q for q in t1_row.question_details if q.question_id == q_b_id
        )
        assert q_b_detail_t1.question_title == "Question B"
        assert q_b_detail_t1.score == 20
        assert q_b_detail_t1.is_solved is False
        assert q_b_detail_t1.attempts == 1
        assert q_b_detail_t1.time_taken_seconds is None

        # Team 2 assertions (Rank 2, Score 50)
        t2_row = response.standings[1]
        assert t2_row.rank == 2
        assert t2_row.team_id == t2_id
        assert t2_row.team_name == "Team 2"
        assert t2_row.total_score == 50
        assert len(t2_row.question_details) == 2

        # Question A for Team 2: Avg of 50 (only accepted member is m21) = 50
        q_a_detail_t2 = next(
            q for q in t2_row.question_details if q.question_id == q_a_id
        )
        assert q_a_detail_t2.question_title == "Question A"
        assert q_a_detail_t2.score == 50
        assert q_a_detail_t2.is_solved is True
        assert q_a_detail_t2.attempts == 2  # includes pending member submission
        assert (
            q_a_detail_t2.time_taken_seconds == 300
        )  # min AC is at 12:05 by pending member

        # Question B for Team 2: Avg of 0 (m21 has unevaluated submission) = 0
        q_b_detail_t2 = next(
            q for q in t2_row.question_details if q.question_id == q_b_id
        )
        assert q_b_detail_t2.question_title == "Question B"
        assert q_b_detail_t2.score == 0
        assert q_b_detail_t2.is_solved is False
        assert q_b_detail_t2.attempts == 1
        assert q_b_detail_t2.time_taken_seconds is None

        # Verify calls
        mock_contest_repository.get_contest_or_raise.assert_called_once_with(
            mock_contest.id
        )
        mock_guard.check_read_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )
        mock_contest_repository.get_contest_leaderboard_raw_data.assert_called_once_with(
            mock_contest.id
        )
