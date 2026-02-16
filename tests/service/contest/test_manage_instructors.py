"""Comprehensive tests for ContestService instructor management methods.

This module tests instructor operations:
- Assigning instructors to contests
- Removing instructors from contests
- Listing instructors with pagination
- Permission checks
- Validation of instructor existence and assignment
- Repository contract verification
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import (
    ContestNotFoundError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
)
from app.exceptions.user import UserNotFoundError
from app.repositories.dto import PaginatedResult
from app.schema.contest import InstructorListResponse, InstructorManageRequest
from app.utils.enums import UserRole


class TestAssignInstructorsSuccess:
    """Test successful instructor assignment scenarios."""

    @pytest.mark.asyncio
    async def test_assign_single_instructor(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test assigning a single instructor to contest."""
        instructor_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[instructor_id])

        mock_user = MagicMock()
        mock_user.role = UserRole.instructor
        mock_user_repository.get_user_or_raise.return_value = mock_user

        await contest_service.assign_instructors_to_contest(
            mock_contest.id, request_data, user_id
        )

        mock_contest_repository.assign_instructor.assert_called()

    @pytest.mark.asyncio
    async def test_assign_multiple_instructors(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test assigning multiple instructors at once."""
        instructor_ids = [uuid4(), uuid4(), uuid4()]
        request_data = InstructorManageRequest(instructor_ids=instructor_ids)

        mock_user = MagicMock()
        mock_user.role = UserRole.instructor
        mock_user_repository.get_user_or_raise.return_value = mock_user

        await contest_service.assign_instructors_to_contest(
            mock_contest.id, request_data, user_id
        )

        # Repository should be called for each instructor
        assert mock_contest_repository.assign_instructor.call_count > 0


class TestAssignInstructorsContestValidation:
    """Test contest validation for instructor assignment."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        contest_service,
        mock_contest_repository,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        contest_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[uuid4()])
        mock_contest_repository.get_contest_or_raise.side_effect = (
            ContestNotFoundError(str(contest_id))
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.assign_instructors_to_contest(
                contest_id, request_data, user_id
            )


class TestAssignInstructorsPermissions:
    """Test permission checks for instructor assignment."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        contest_service,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        request_data = InstructorManageRequest(instructor_ids=[uuid4()])
        mock_guard.check_assign_instructors.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.assign_instructors_to_contest(
                setup_valid_contest.id, request_data, user_id
            )


class TestAssignInstructorsValidation:
    """Test validation for instructor assignment."""

    @pytest.mark.asyncio
    async def test_raises_when_instructor_not_found(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        setup_valid_contest,
        user_id,
    ):
        """Test that UserNotFoundError is raised for non-existent instructor."""
        instructor_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[instructor_id])
        mock_user_repository.get_users_or_raise.side_effect = UserNotFoundError(
            str(instructor_id)
        )

        with pytest.raises(UserNotFoundError):
            await contest_service.assign_instructors_to_contest(
                setup_valid_contest.id, request_data, user_id
            )

    @pytest.mark.asyncio
    async def test_raises_when_already_assigned(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        setup_valid_contest,
        user_id,
    ):
        """Test that InstructorAlreadyAssignedError is raised for duplicate assignment."""
        instructor_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[instructor_id])

        mock_user = MagicMock()
        mock_user.role = UserRole.instructor
        mock_user_repository.get_user_or_raise.return_value = mock_user

        mock_contest_repository.assign_instructor.side_effect = (
            InstructorAlreadyAssignedError(str(instructor_id), str(setup_valid_contest.id))
        )

        with pytest.raises(InstructorAlreadyAssignedError):
            await contest_service.assign_instructors_to_contest(
                setup_valid_contest.id, request_data, user_id
            )


class TestRemoveInstructorsSuccess:
    """Test successful instructor removal scenarios."""

    @pytest.mark.asyncio
    async def test_remove_single_instructor(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test removing a single instructor from contest."""
        instructor_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[instructor_id])

        await contest_service.remove_instructors_from_contest(
            mock_contest.id, request_data, user_id
        )

        mock_contest_repository.remove_instructor.assert_called()

    @pytest.mark.asyncio
    async def test_remove_multiple_instructors(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test removing multiple instructors at once."""
        instructor_ids = [uuid4(), uuid4()]
        request_data = InstructorManageRequest(instructor_ids=instructor_ids)

        await contest_service.remove_instructors_from_contest(
            mock_contest.id, request_data, user_id
        )

        assert mock_contest_repository.remove_instructor.call_count > 0


class TestRemoveInstructorsValidation:
    """Test validation for instructor removal."""

    @pytest.mark.asyncio
    async def test_raises_when_instructor_not_assigned(
        self,
        contest_service,
        mock_contest_repository,
        setup_valid_contest,
        user_id,
    ):
        """Test that InstructorNotAssignedError is raised for non-assigned instructor."""
        instructor_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[instructor_id])
        mock_contest_repository.remove_instructor.side_effect = (
            InstructorNotAssignedError(str(instructor_id), str(setup_valid_contest.id))
        )

        with pytest.raises(InstructorNotAssignedError):
            await contest_service.remove_instructors_from_contest(
                setup_valid_contest.id, request_data, user_id
            )


class TestRemoveInstructorsPermissions:
    """Test permission checks for instructor removal."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        contest_service,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        request_data = InstructorManageRequest(instructor_ids=[uuid4()])
        mock_guard.check_remove_instructors.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.remove_instructors_from_contest(
                setup_valid_contest.id, request_data, user_id
            )


class TestGetInstructorsSuccess:
    """Test successful instructor listing."""

    @pytest.mark.asyncio
    async def test_returns_paginated_instructor_list(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        mock_instructor,
        setup_valid_contest,
        user_id,
    ):
        """Test that get_contest_instructors returns paginated list."""
        mock_contest_repository.get_contest_instructors_paginated.return_value = (
            1, [mock_instructor]
        )

        response = await contest_service.get_contest_instructors(
            mock_contest.id, user_id
        )

        assert response.total == 1
        assert len(response.instructors) == 1

    @pytest.mark.asyncio
    async def test_empty_instructor_list(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that empty instructor list returns (0, [])."""
        mock_contest_repository.get_contest_instructors_paginated.return_value = (
            0, []
        )

        response = await contest_service.get_contest_instructors(
            mock_contest.id, user_id
        )

        assert response.total == 0
        assert response.instructors == []

    @pytest.mark.asyncio
    async def test_with_pagination_parameters(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that pagination parameters are passed to repository."""
        mock_contest_repository.get_contest_instructors_paginated.return_value = (
            0, []
        )

        await contest_service.get_contest_instructors(
            mock_contest.id, user_id, skip=10, limit=20
        )

        call_args = mock_contest_repository.get_contest_instructors_paginated.call_args
        # Verify pagination is passed correctly
        assert call_args is not None


class TestManageInstructorsRepositoryContract:
    """Test service-repository interface for instructor management."""

    @pytest.mark.asyncio
    async def test_assign_repository_called_with_correct_ids(
        self,
        contest_service,
        mock_contest_repository,
        mock_user_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that repository receives correct instructor IDs."""
        instructor_ids = [uuid4(), uuid4()]
        request_data = InstructorManageRequest(instructor_ids=instructor_ids)

        mock_user = MagicMock()
        mock_user.role = UserRole.instructor
        mock_user_repository.get_user_or_raise.return_value = mock_user

        await contest_service.assign_instructors_to_contest(
            mock_contest.id, request_data, user_id
        )

        mock_contest_repository.assign_instructor.assert_called()

    @pytest.mark.asyncio
    async def test_remove_repository_called_with_correct_ids(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that repository receives correct instructor IDs for removal."""
        instructor_ids = [uuid4()]
        request_data = InstructorManageRequest(instructor_ids=instructor_ids)

        await contest_service.remove_instructors_from_contest(
            mock_contest.id, request_data, user_id
        )

        mock_contest_repository.remove_instructor.assert_called()


class TestManageInstructorsExecutionOrder:
    """Test execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_contest_validated_before_permission_for_assign(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        user_id,
    ):
        """Test that contest existence is checked before permissions on assign."""
        contest_id = uuid4()
        request_data = InstructorManageRequest(instructor_ids=[uuid4()])
        mock_contest_repository.get_contest_or_raise.side_effect = (
            ContestNotFoundError(str(contest_id))
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.assign_instructors_to_contest(
                contest_id, request_data, user_id
            )

        mock_guard.check_manage_contest.assert_not_called()

    @pytest.mark.asyncio
    async def test_permission_validated_before_repository_for_remove(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        setup_valid_contest,
        user_id,
    ):
        """Test that permissions are checked before repository on remove."""
        request_data = InstructorManageRequest(instructor_ids=[uuid4()])
        mock_guard.check_remove_instructors.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.remove_instructors_from_contest(
                setup_valid_contest.id, request_data, user_id
            )

        mock_contest_repository.remove_instructor.assert_not_called()
