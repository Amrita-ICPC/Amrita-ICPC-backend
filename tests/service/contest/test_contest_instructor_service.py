from datetime import datetime, timezone
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import (
    ContestNotFoundError,
    InstructorAlreadyAssignedError,
    InstructorNotAssignedError,
)
from app.exceptions.user import UserNotFoundError

# Models imported to ensure SQLAlchemy mapper registry is populated
from app.schema.contest import InstructorManageRequest
from app.utils.enums import UserRole

if TYPE_CHECKING:
    from app.service.contest_service import ContestService


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_contest_repository():
    from app.repositories.contest import ContestRepository

    mock = MagicMock(spec=ContestRepository)
    # Add db attribute for is_admin checks
    mock.db = MagicMock(spec=Session)
    return mock


@pytest.fixture
def mock_user_repository():
    from app.repositories.user import UserRepository

    return MagicMock(spec=UserRepository)


@pytest.fixture
def mock_guard():
    from app.core.guards.contest import ContestOperationGuard

    return MagicMock(spec=ContestOperationGuard)


@pytest.fixture
def mock_validator():
    from app.validators.contest import ContestValidator

    return MagicMock(spec=ContestValidator)


@pytest.fixture
def contest_service(
    mock_contest_repository, mock_user_repository, mock_guard, mock_validator
):
    # Patch the cache decorators to avoid redis connection issues
    with (
        patch(
            "app.core.cache.decorators.cache_get",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_set",
            side_effect=lambda **kwargs: lambda func: func,
        ),
        patch(
            "app.core.cache.decorators.cache_delete",
            side_effect=lambda **kwargs: lambda func: func,
        ),
    ):
        from app.service.contest_service import ContestService

        service = ContestService(
            mock_contest_repository, mock_user_repository, mock_guard, mock_validator
        )
        yield service


class MockContest:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockUser:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockContestInstructor:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def mock_contest():
    contest_id = uuid4()
    creator_id = uuid4()
    return MockContest(
        id=contest_id,
        name="Test Contest",
        description="A test contest",
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_instructor():
    instructor_id = uuid4()
    return MockUser(
        id=instructor_id,
        user_id="instructor123",
        name="John Instructor",
        email="instructor@test.com",
        role=UserRole.instructor,
        phone_no="1234567890",
        gender="Male",
        dob=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_creator():
    creator_id = uuid4()
    return MockUser(
        id=creator_id,
        user_id="creator123",
        name="Jane Creator",
        email="creator@test.com",
        role=UserRole.admin,
        phone_no="0987654321",
        gender="Female",
        dob=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_assign_instructors_to_contest_success(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_user_repository,
    mock_guard,
    mock_validator,
    mock_contest,
    mock_instructor,
):
    """Test successful assignment of instructors to contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock repository methods
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_users_or_raise.return_value = [mock_instructor]
    mock_contest_repository.get_all_instructors_for_contest.return_value = []
    mock_validator.validate_instructors_not_in_contest.return_value = None

    await contest_service.assign_instructors_to_contest(
        mock_contest.id, request, user_id
    )

    mock_guard.check_assign_instructors.assert_called_once()
    mock_user_repository.get_users_or_raise.assert_called_once_with(
        [mock_instructor.id]
    )
    mock_contest_repository.get_all_instructors_for_contest.assert_called_once_with(
        mock_contest.id
    )
    mock_validator.validate_instructors_not_in_contest.assert_called_once_with(
        [], [mock_instructor.id]
    )
    mock_contest_repository.assign_instructor.assert_called_once_with(
        mock_contest.id, [mock_instructor.id]
    )


@pytest.mark.asyncio
async def test_assign_instructors_to_contest_not_found(
    contest_service: "ContestService", mock_contest_repository, mock_instructor
):
    """Test assigning instructors to non-existent contest."""
    contest_id = uuid4()
    user_id = uuid4()
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock contest not found
    mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
        contest_id
    )

    with pytest.raises(ContestNotFoundError):
        await contest_service.assign_instructors_to_contest(
            contest_id, request, user_id
        )


@pytest.mark.asyncio
async def test_assign_instructors_instructor_not_found(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_user_repository,
    mock_guard,
    mock_contest,
):
    """Test assigning non-existent instructor to contest."""
    instructor_id = uuid4()
    InstructorManageRequest(instructor_ids=[instructor_id])

    # Mock contest found but instructor not found
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_users_or_raise.side_effect = UserNotFoundError(
        instructor_id
    )


@pytest.mark.asyncio
async def test_assign_instructors_already_assigned(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_user_repository,
    mock_guard,
    mock_validator,
    mock_contest,
    mock_instructor,
):
    """Test assigning instructor who is already assigned to contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock repository methods
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_users_or_raise.return_value = [mock_instructor]
    mock_contest_repository.get_all_instructors_for_contest.return_value = [
        mock_instructor
    ]
    mock_validator.validate_instructors_not_in_contest.side_effect = (
        InstructorAlreadyAssignedError(str(mock_instructor.id), str(mock_contest.id))
    )

    with pytest.raises(InstructorAlreadyAssignedError):
        await contest_service.assign_instructors_to_contest(
            mock_contest.id, request, user_id
        )


@pytest.mark.asyncio
async def test_assign_instructors_permission_denied(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_guard,
    mock_contest,
    mock_instructor,
):
    """Test assigning instructors without permission."""
    user_id = uuid4()  # Different user
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock repository methods
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_guard.check_assign_instructors.side_effect = PermissionDeniedError(
        "Permission denied"
    )

    with pytest.raises(PermissionDeniedError):
        await contest_service.assign_instructors_to_contest(
            mock_contest.id, request, user_id
        )


@pytest.mark.asyncio
async def test_remove_instructors_from_contest_success(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_guard,
    mock_validator,
    mock_contest,
    mock_instructor,
    mock_user_repository,
):
    """Test successful removal of instructors from contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock repository methods
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_users_or_raise.return_value = [mock_instructor]
    mock_contest_repository.get_all_instructors_for_contest.return_value = [
        mock_instructor
    ]
    mock_validator.validate_instructors_in_contest.return_value = None

    await contest_service.remove_instructors_from_contest(
        mock_contest.id, request, user_id
    )

    mock_guard.check_remove_instructors.assert_called_once()
    mock_user_repository.get_users_or_raise.assert_called_once_with(
        [mock_instructor.id]
    )
    mock_contest_repository.get_all_instructors_for_contest.assert_called_once_with(
        mock_contest.id
    )
    mock_validator.validate_instructors_in_contest.assert_called_once_with(
        {mock_instructor.id}, {mock_instructor.id}
    )
    mock_contest_repository.remove_instructor.assert_called_once_with(
        mock_contest.id, [mock_instructor.id]
    )


@pytest.mark.asyncio
async def test_remove_instructors_not_assigned(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_guard,
    mock_validator,
    mock_contest,
    mock_instructor,
    mock_user_repository,
):
    """Test removing instructor who is not assigned to contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock repository methods
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_user_repository.get_users_or_raise.return_value = [mock_instructor]
    mock_contest_repository.get_all_instructors_for_contest.return_value = []  # No instructors assigned
    mock_validator.validate_instructors_in_contest.side_effect = (
        InstructorNotAssignedError(str(mock_instructor.id), str(mock_contest.id))
    )

    with pytest.raises(InstructorNotAssignedError):
        await contest_service.remove_instructors_from_contest(
            mock_contest.id, request, user_id
        )


@pytest.mark.asyncio
async def test_get_contest_instructors_success(
    contest_service: "ContestService",
    mock_contest_repository,
    mock_guard,
    mock_contest,
    mock_instructor,
    mock_creator,
):
    """Test getting instructors for a contest."""
    user_id = mock_contest.created_by  # Use creator as user for permission

    # Mock repository methods
    mock_contest_repository.get_contest_or_raise.return_value = mock_contest
    mock_contest_repository.get_contest_instructors_paginated.return_value = (
        1,
        [mock_instructor],
    )
    mock_contest_repository.get_creator.return_value = mock_creator

    result = await contest_service.get_contest_instructors(mock_contest.id, user_id)

    mock_guard.check_manage_contest.assert_called_once()
    assert result.total == 1
    assert len(result.instructors) == 1
    assert result.instructors[0].id == mock_instructor.id
    assert result.creator is not None
    assert result.creator.id == mock_creator.id


@pytest.mark.asyncio
async def test_get_contest_instructors_contest_not_found(
    contest_service: "ContestService", mock_contest_repository
):
    """Test getting instructors for non-existent contest."""
    contest_id = uuid4()
    user_id = uuid4()

    # Mock contest not found
    mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
        contest_id
    )

    with pytest.raises(ContestNotFoundError):
        await contest_service.get_contest_instructors(contest_id, user_id)


@pytest.mark.asyncio
async def test_contest_permission_creator_can_manage(mock_db, mock_contest):
    """Test that contest creator has permission to manage contest."""
    from app.core.permissions import ContestPermission

    creator_id = mock_contest.created_by

    # Mock query for ContestInstructor check (not needed since creator always allowed)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Should not raise exception for creator
    ContestPermission.can_manage_contest(
        mock_db, user_id=creator_id, contest=mock_contest
    )


@pytest.mark.asyncio
async def test_contest_permission_instructor_can_manage(
    mock_db, mock_contest, mock_instructor
):
    """Test that assigned instructor has permission to manage contest."""
    from app.core.permissions import ContestPermission

    # Create assignment record
    assignment = MockContestInstructor(
        contest_id=mock_contest.id, instructor_id=mock_instructor.id
    )

    # Mock query for ContestInstructor check
    mock_db.query.return_value.filter.return_value.first.return_value = assignment

    # Should not raise exception for assigned instructor
    ContestPermission.can_manage_contest(
        mock_db, user_id=mock_instructor.id, contest=mock_contest
    )


@pytest.mark.asyncio
async def test_contest_permission_non_assigned_user_cannot_manage(
    mock_db, mock_contest
):
    """Test that non-assigned user cannot manage contest."""
    from app.core.permissions import ContestPermission

    random_user_id = uuid4()

    # Mock query for ContestInstructor check (no assignment found)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Should raise PermissionDeniedError for non-assigned user
    with pytest.raises(PermissionDeniedError):
        ContestPermission.can_manage_contest(
            mock_db, user_id=random_user_id, contest=mock_contest
        )
