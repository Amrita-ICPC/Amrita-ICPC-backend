from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.repositories.submission import ContestSubmissionRepository
from app.repositories.team import TeamRepository
from app.schema.submission import ContestDashboardResponse
from app.service.contest_dashboard_service import ContestDashboardService
from app.utils.enums import ContestStatus


@pytest.fixture
def mock_submission_repository():
    """Mock ContestSubmissionRepository."""
    return AsyncMock(spec=ContestSubmissionRepository)


@pytest.fixture
def mock_team_repository():
    """Mock TeamRepository."""
    return AsyncMock(spec=TeamRepository)


@pytest.fixture
def dashboard_service(
    mock_contest_repository,
    mock_submission_repository,
    mock_guard,
    mock_team_repository,
):
    """Instantiate ContestDashboardService with mocked dependencies."""
    return ContestDashboardService(
        contest_repository=mock_contest_repository,
        submission_repository=mock_submission_repository,
        guard=mock_guard,
        team_repository=mock_team_repository,
    )


class TestGetContestDashboardSuccess:
    """Test successful retrieval of contest dashboard analytics."""

    @pytest.mark.asyncio
    async def test_returns_dashboard_response(
        self,
        dashboard_service,
        mock_contest_repository,
        mock_submission_repository,
        mock_contest,
        user_id,
    ):
        """Test that successful retrieval returns ContestDashboardResponse."""
        from app.repositories.dto.submission import (
            ContestAnalyticsRaw,
            ContestDashboardRawData,
        )

        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.status = ContestStatus.PUBLISHED

        mock_raw_data = ContestDashboardRawData(
            analytics=ContestAnalyticsRaw(
                total_submissions=10,
                accepted=4,
                wrong_answer=3,
                time_limit_exceeded=1,
                runtime_error=1,
                compilation_error=1,
                memory_limit_exceeded=0,
                system_error=0,
            ),
            problem_health=[],
            team_performance=[],
            recent_submissions=[],
        )
        mock_submission_repository.get_dashboard_analytics_raw.return_value = (
            mock_raw_data
        )

        result = await dashboard_service.get_dashboard_analytics(
            mock_contest.id, user_id
        )

        assert isinstance(result, ContestDashboardResponse)
        assert result.contest_analytics.total_submissions == 10
        assert result.contest_analytics.accepted == 4
        mock_contest_repository.get_contest_or_raise.assert_called_once_with(
            mock_contest.id
        )
        mock_submission_repository.get_dashboard_analytics_raw.assert_called_once_with(
            mock_contest.id
        )


class TestGetContestDashboardValidation:
    """Test validation and existence checks for dashboard retrieval."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        dashboard_service,
        mock_contest_repository,
        user_id,
    ):
        """Test that ContestNotFoundError is raised if the contest does not exist."""
        contest_id = uuid4()
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await dashboard_service.get_dashboard_analytics(contest_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_when_contest_is_soft_deleted(
        self,
        dashboard_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that ContestNotFoundError is raised if the contest status is DELETED."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.status = ContestStatus.DELETED

        with pytest.raises(ContestNotFoundError):
            await dashboard_service.get_dashboard_analytics(mock_contest.id, user_id)


class TestGetContestDashboardPermissions:
    """Test permission validation for dashboard retrieval."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        dashboard_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised if the guard checks fail."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.status = ContestStatus.PUBLISHED
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError(
            "Lacks manage permission"
        )

        with pytest.raises(PermissionDeniedError):
            await dashboard_service.get_dashboard_analytics(mock_contest.id, user_id)

        mock_guard.check_manage_contest.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )
