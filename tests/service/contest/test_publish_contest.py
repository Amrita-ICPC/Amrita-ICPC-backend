"""Comprehensive tests for ContestService.publish_contest method.

This module tests contest publishing operations:
- Successful publishing with status and timestamp updates
- Permission checks
- Execution order validation
- Repository contract verification
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.utils.enums import ContestStatus


class TestPublishContestSuccess:
    """Test successful contest publishing scenarios."""

    @pytest.mark.asyncio
    async def test_publish_updates_contest_status(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that publish operation updates contest status."""
        mock_contest.status = ContestStatus.DRAFT

        await contest_service.publish_contest(mock_contest.id, user_id)

        mock_contest_repository.publish_contest.assert_called_once_with(
            mock_contest, user_id
        )

    @pytest.mark.asyncio
    async def test_can_republish_running_contest(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that already running contests can be republished."""
        mock_contest.status = ContestStatus.PUBLISHED

        await contest_service.publish_contest(mock_contest.id, user_id)

        mock_contest_repository.publish_contest.assert_called_once()


class TestPublishContestValidation:
    """Test contest validation for publishing."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
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
            await contest_service.publish_contest(contest_id, user_id)


class TestPublishContestPermissions:
    """Test permission validation for publishing."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
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
            await contest_service.publish_contest(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        published_contest = MagicMock()
        mock_contest_repository.publish_contest.return_value = published_contest

        await contest_service.publish_contest(mock_contest.id, user_id)

        mock_guard.check_manage_contest.assert_called_once()
        call_args = mock_guard.check_manage_contest.call_args
        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["contest"] == mock_contest


class TestPublishContestExecutionOrder:
    """Test execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_contest_validated_before_guard(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        user_id,
    ):
        """Test that contest existence is checked before permissions."""
        contest_id = uuid4()
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.publish_contest(contest_id, user_id)

        mock_guard.check_manage_contest.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_checked_before_repository_publish(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that permissions are checked before publishing."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.publish_contest(setup_valid_contest.id, user_id)

        mock_contest_repository.publish_contest.assert_not_called()


class TestPublishContestRepositoryContract:
    """Test service-repository interface for publishing."""

    @pytest.mark.asyncio
    async def test_repository_publish_called_with_contest_and_user(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that repository.publish_contest receives contest and user_id."""
        published_contest = MagicMock()
        mock_contest_repository.publish_contest.return_value = published_contest

        await contest_service.publish_contest(mock_contest.id, user_id)

        mock_contest_repository.publish_contest.assert_called_once()
        call_args = mock_contest_repository.publish_contest.call_args[0]
        assert call_args[0] == mock_contest
        assert call_args[1] == user_id

    @pytest.mark.asyncio
    async def test_repository_never_called_when_permission_denied(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that repository operations are never called when permission denied."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.publish_contest(setup_valid_contest.id, user_id)

        mock_contest_repository.publish_contest.assert_not_called()


class TestPublishContestSoftDelete:
    """Test that soft-deleted contests cannot be published."""

    @pytest.mark.asyncio
    async def test_soft_deleted_contest_raises_not_found(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that soft-deleted contests raise ContestNotFoundError."""
        mock_contest.is_deleted = True
        mock_contest.status = ContestStatus.DELETED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        with pytest.raises(ContestNotFoundError):
            await contest_service.publish_contest(mock_contest.id, user_id)
