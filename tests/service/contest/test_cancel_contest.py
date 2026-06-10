"""Comprehensive tests for ContestService.cancel_contest method."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.schema.contest import ContestEvent
from app.utils.enums import ContestStatus


class TestCancelContestSuccess:
    """Test successful contest cancellation scenarios."""

    @pytest.mark.asyncio
    async def test_cancel_updates_contest_status(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that cancel operation updates contest status to CANCELLED and saves via update_contest."""
        mock_contest.status = ContestStatus.DRAFT

        # Verify initial state
        assert mock_contest.status != ContestStatus.CANCELLED

        await contest_service.cancel_contest(mock_contest.id, user_id)

        # Assert status was set to CANCELLED
        assert mock_contest.status == ContestStatus.CANCELLED

        # Assert update_contest repository function was called with modified contest object
        mock_contest_repository.update_contest.assert_called_once_with(
            mock_contest, user_id
        )

    @pytest.mark.asyncio
    async def test_cancel_publishes_event(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that cancel operation publishes a CANCELLED event if event_publisher is set."""
        mock_contest.status = ContestStatus.DRAFT
        mock_publisher = AsyncMock()
        contest_service.event_publisher = mock_publisher

        await contest_service.cancel_contest(mock_contest.id, user_id)

        mock_publisher.publish.assert_called_once()
        call_args = mock_publisher.publish.call_args
        assert call_args[0][0] == mock_contest.id
        event = call_args[0][1]
        assert isinstance(event, ContestEvent)
        assert event.type == "CANCELLED"
        assert event.payload["contest_id"] == str(mock_contest.id)


class TestCancelContestValidation:
    """Test validation constraints for contest cancellation."""

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
            await contest_service.cancel_contest(contest_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_when_contest_deleted(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest status is DELETED."""
        mock_contest.status = ContestStatus.DELETED
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest

        with pytest.raises(ContestNotFoundError):
            await contest_service.cancel_contest(mock_contest.id, user_id)


class TestCancelContestPermissions:
    """Test permission validation for contest cancellation."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        contest_service,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks manage permissions."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()
        mock_contest = setup_valid_contest

        with pytest.raises(PermissionDeniedError):
            await contest_service.cancel_contest(mock_contest.id, user_id)
