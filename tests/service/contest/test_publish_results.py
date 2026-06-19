"""Tests for ContestService.publish_results method."""

from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.utils.enums import ContestStatus


class TestPublishResults:
    """Test suite for publish_results service method."""

    @pytest.mark.asyncio
    async def test_publish_results_success(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test successful publishing of results."""
        mock_contest.results_published = False
        mock_contest_repository.update_contest.return_value = mock_contest

        await contest_service.publish_results(mock_contest.id, True, user_id)

        assert mock_contest.results_published is True
        mock_contest_repository.update_contest.assert_called_once_with(
            mock_contest, user_id
        )

    @pytest.mark.asyncio
    async def test_unpublish_results_success(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test successful unpublishing of results."""
        mock_contest.results_published = True
        mock_contest_repository.update_contest.return_value = mock_contest

        await contest_service.publish_results(mock_contest.id, False, user_id)

        assert mock_contest.results_published is False
        mock_contest_repository.update_contest.assert_called_once_with(
            mock_contest, user_id
        )

    @pytest.mark.asyncio
    async def test_publish_results_not_found(
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
            await contest_service.publish_results(contest_id, True, user_id)

    @pytest.mark.asyncio
    async def test_publish_results_deleted_contest(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that soft-deleted contests raise ContestNotFoundError."""
        mock_contest.status = ContestStatus.DELETED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        with pytest.raises(ContestNotFoundError):
            await contest_service.publish_results(mock_contest.id, True, user_id)

    @pytest.mark.asyncio
    async def test_publish_results_permission_denied(
        self,
        contest_service,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()
        mock_contest = setup_valid_contest

        with pytest.raises(PermissionDeniedError):
            await contest_service.publish_results(mock_contest.id, True, user_id)
