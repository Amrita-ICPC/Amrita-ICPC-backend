"""Comprehensive tests for ContestService contest retrieval methods.

This module tests contest retrieval operations using the repository,
guard, and validator patterns. Tests are organized by method and validation concern.

Methods Under Test:
    - get_contest_by_id: Retrieve a specific contest by ID with permission checks
    - get_all_contests: Retrieve contests with filtering, search, and pagination

Test Organization:
    Each method has dedicated test classes covering:
    - Success scenarios with various parameter combinations
    - Contest existence validation
    - Soft delete handling
    - Permission validation via ContestOperationGuard
    - Repository contract verification
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.repositories.dto import PaginatedResult
from app.schema.contest import ContestResponse, ContestSummaryResponse
from app.utils.enums import ContestStatus, UserRole


class TestGetContestByIdSuccess:
    """Test successful contest retrieval scenarios."""

    @pytest.mark.asyncio
    async def test_returns_contest_response(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that successful retrieval returns ContestResponse."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.is_deleted = False

        with patch.object(
            ContestResponse,
            "model_validate",
            return_value=MagicMock(spec=ContestResponse),
        ):
            result = await contest_service.get_contest_by_id(mock_contest.id, user_id)

        assert result is not None
        mock_contest_repository.get_contest_or_raise.assert_called_once_with(
            mock_contest.id
        )

    @pytest.mark.asyncio
    async def test_skips_soft_deleted_contests(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that soft-deleted contests are not retrievable."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.is_deleted = True
        mock_contest.status = ContestStatus.DELETED

        with pytest.raises(ContestNotFoundError):
            await contest_service.get_contest_by_id(mock_contest.id, user_id)

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.is_deleted = False

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.get_contest_by_id(mock_contest.id, user_id)

        mock_guard.check_read_contest.assert_called_once()
        call_args = mock_guard.check_read_contest.call_args
        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["contest"] == mock_contest


class TestGetContestByIdValidation:
    """Test contest existence validation."""

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
            await contest_service.get_contest_by_id(contest_id, user_id)


class TestGetContestByIdPermissions:
    """Test permission validation for contest retrieval."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        mock_contest_repository.get_contest_or_raise.return_value = mock_contest
        mock_contest.is_deleted = False
        mock_guard.check_read_contest.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.get_contest_by_id(mock_contest.id, user_id)


class TestGetAllContestsSuccess:
    """Test successful contest list retrieval."""

    @pytest.mark.asyncio
    async def test_returns_tuple_with_count_and_contests(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_contest,
        mock_user,
        user_id,
    ):
        """Test that get_all_contests returns (total_count, list[ContestSummaryResponse])."""
        mock_result = PaginatedResult(total=1, items=[mock_contest])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user_repository.get_user_or_raise.return_value = mock_user
        mock_user.role = UserRole.student

        with patch.object(
            ContestSummaryResponse,
            "model_validate",
            side_effect=lambda x: x,
        ):
            total, contests = await contest_service.get_all_contests(user_id)

        assert total == 1
        assert len(contests) == 1
        assert isinstance(contests[0], ContestSummaryResponse)
        assert contests[0].id == mock_contest.id

    @pytest.mark.asyncio
    async def test_empty_results_returns_zero_count(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that empty results return (0, [])."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user_repository.get_user_or_raise.return_value = mock_user
        mock_user.role = UserRole.student

        total, contests = await contest_service.get_all_contests(user_id)

        assert total == 0
        assert contests == []

    @pytest.mark.asyncio
    async def test_with_search_term_filters_correctly(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that search_term parameter is passed to repository."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user_repository.get_user_or_raise.return_value = mock_user
        mock_user.role = UserRole.student

        await contest_service.get_all_contests(user_id, search_term="Alpha")

        call_args = mock_contest_repository.get_contests_with_filters.call_args
        filters = call_args[0][2]
        assert filters.search_term == "Alpha"

    @pytest.mark.asyncio
    async def test_with_status_filter_returns_matching(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that status filter is passed to repository."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user_repository.get_user_or_raise.return_value = mock_user
        mock_user.role = UserRole.student

        await contest_service.get_all_contests(user_id, status=ContestStatus.PUBLISHED)

        call_args = mock_contest_repository.get_contests_with_filters.call_args
        filters = call_args[0][2]
        assert filters.status == ContestStatus.PUBLISHED

    @pytest.mark.asyncio
    async def test_with_pagination_returns_correct_page(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that pagination parameters are passed correctly."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user_repository.get_user_or_raise.return_value = mock_user
        mock_user.role = UserRole.student

        await contest_service.get_all_contests(user_id, skip=10, limit=20)

        call_args = mock_contest_repository.get_contests_with_filters.call_args
        pagination = call_args[0][3]
        assert pagination.skip == 10
        assert pagination.limit == 20


class TestGetAllContestsUserRoles:
    """Test different user access levels."""

    @pytest.mark.asyncio
    async def test_admin_user_is_detected(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that admin status is passed to repository."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user.role = UserRole.admin
        mock_user_repository.get_user_or_raise.return_value = mock_user

        await contest_service.get_all_contests(user_id)

        call_args = mock_contest_repository.get_contests_with_filters.call_args
        is_admin = call_args[0][1]
        assert is_admin is True

    @pytest.mark.asyncio
    async def test_non_admin_user_is_detected(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that non-admin status is detected."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user.role = UserRole.student
        mock_user_repository.get_user_or_raise.return_value = mock_user

        await contest_service.get_all_contests(user_id)

        call_args = mock_contest_repository.get_contests_with_filters.call_args
        is_admin = call_args[0][1]
        assert is_admin is False


class TestGetAllContestsRepositoryContract:
    """Test the interface between service and repository."""

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_arguments(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_user,
        user_id,
    ):
        """Test that repository is called with correct user and filters."""
        mock_result = PaginatedResult(total=0, items=[])
        mock_contest_repository.get_contests_with_filters.return_value = mock_result
        mock_user.role = UserRole.student
        mock_user_repository.get_user_or_raise.return_value = mock_user

        await contest_service.get_all_contests(
            user_id,
            search_term="test",
            status=ContestStatus.DRAFT,
            is_public=True,
            skip=5,
            limit=10,
        )

        mock_contest_repository.get_contests_with_filters.assert_called_once()
        call_args = mock_contest_repository.get_contests_with_filters.call_args
        assert call_args[0][0] == user_id
        assert call_args[0][1] is False  # not admin
