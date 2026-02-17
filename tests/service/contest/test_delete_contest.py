"""Comprehensive tests for ContestService delete/restore operations.

This module tests soft delete and restore functionality:
- Successful deletion with flag setting
- Restoration of soft-deleted contests
- Permission checks for both operations
- Repository contract verification
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.schema.contest import ContestResponse
from app.utils.enums import UserRole


class TestDeleteContestSuccess:
    """Test successful contest deletion scenarios."""

    @pytest.mark.asyncio
    async def test_delete_sets_soft_delete_flags(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that delete operation calls repository with correct contest."""
        deleted_contest = MagicMock()
        deleted_contest.id = mock_contest.id
        deleted_contest.is_deleted = True
        mock_contest_repository.delete_contest.return_value = deleted_contest

        with patch.object(ContestResponse, "model_validate"):
            result = await contest_service.delete_contest(mock_contest.id, user_id)

        assert result is not None
        mock_contest_repository.delete_contest.assert_called_once_with(mock_contest)


class TestDeleteContestValidation:
    """Test contest validation for deletion."""

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
            await contest_service.delete_contest(contest_id, user_id)


class TestDeleteContestPermissions:
    """Test permission checks for deletion."""

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
            await contest_service.delete_contest(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_guard_called_before_delete(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that permissions are checked before deletion."""
        deleted_contest = MagicMock()
        mock_contest_repository.delete_contest.return_value = deleted_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.delete_contest(mock_contest.id, user_id)

        # Guard should be called before repository
        assert mock_guard.check_manage_contest.called
        assert mock_contest_repository.delete_contest.called


class TestRestoreContestSuccess:
    """Test successful restoration of soft-deleted contests."""

    @pytest.mark.asyncio
    async def test_restore_clears_soft_delete_flags(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that restore operation restores deleted contest."""
        mock_contest.is_deleted = True
        restored_contest = MagicMock()
        restored_contest.id = mock_contest.id
        restored_contest.is_deleted = False
        mock_contest_repository.restore_contest.return_value = restored_contest

        with patch.object(ContestResponse, "model_validate"):
            result = await contest_service.restore_contest(mock_contest.id, user_id)

        assert result is not None
        mock_contest_repository.restore_contest.assert_called_once_with(mock_contest)


class TestRestoreContestValidation:
    """Test validation for restore operations."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        contest_service,
        mock_contest_repository,
        user_id,
    ):
        """Test that ContestNotFoundError is raised for non-existent contest."""
        contest_id = uuid4()
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.restore_contest(contest_id, user_id)


class TestRestoreContestPermissions:
    """Test permission checks for restore operations."""

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
            await contest_service.restore_contest(mock_contest.id, user_id)


class TestDeleteContestRepositoryContract:
    """Test service-repository interface for deletion."""

    @pytest.mark.asyncio
    async def test_repository_delete_called_with_contest_object(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that repository.delete_contest receives contest object."""
        deleted_contest = MagicMock()
        mock_contest_repository.delete_contest.return_value = deleted_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.delete_contest(mock_contest.id, user_id)

        # Repository should be called with the contest object
        mock_contest_repository.delete_contest.assert_called_once()
        call_args = mock_contest_repository.delete_contest.call_args[0]
        assert call_args[0] == mock_contest

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
        mock_contest = setup_valid_contest

        with pytest.raises(PermissionDeniedError):
            await contest_service.delete_contest(mock_contest.id, user_id)

        mock_contest_repository.delete_contest.assert_not_called()


class TestGetSoftDeletedContests:
    """Test retrieving soft-deleted contests."""

    @pytest.mark.asyncio
    async def test_returns_deleted_contests(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_contest,
        mock_user,
        user_id,
    ):
        """Test that soft-deleted contests can be retrieved."""
        from app.repositories.dto import PaginatedResult

        mock_contest.is_deleted = True
        mock_result = PaginatedResult(total=1, items=[mock_contest])
        mock_contest_repository.get_soft_deleted_contests.return_value = mock_result
        mock_user.role = UserRole.student
        mock_user_repository.get_user_or_raise.return_value = mock_user

        from app.schema.contest import ContestSummaryResponse

        with patch.object(
            ContestSummaryResponse, "model_validate", side_effect=lambda x: x
        ):
            total, contests = await contest_service.get_soft_deleted_contests(user_id)

        assert total == 1
        assert len(contests) == 1
