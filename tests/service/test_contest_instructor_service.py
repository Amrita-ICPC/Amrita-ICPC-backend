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
from app.models.contest import Contest, ContestInstructor
from app.models.user import User
from app.schema.contest import InstructorManageRequest
from app.utils.enums import UserRole

if TYPE_CHECKING:
    from app.service.contest_service import ContestService


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def contest_service(mock_db):
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

        service = ContestService(mock_db)
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
    contest_service: "ContestService", mock_db, mock_contest, mock_instructor
):
    """Test successful assignment of instructors to contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        elif model == User:
            mock.filter.return_value.first.return_value = mock_instructor
        elif model == ContestInstructor:
            # No existing assignment
            mock.filter.return_value.first.return_value = None
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest"
    ) as mock_perm:
        await contest_service.assign_instructors_to_contest(
            mock_contest.id, request, user_id
        )
        mock_perm.assert_called_once()

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_assign_instructors_to_contest_not_found(
    contest_service: "ContestService", mock_db, mock_instructor
):
    """Test assigning instructors to non-existent contest."""
    contest_id = uuid4()
    user_id = uuid4()
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Mock contest not found
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = None
        return mock

    mock_db.query.side_effect = query_side_effect

    with pytest.raises(ContestNotFoundError):
        await contest_service.assign_instructors_to_contest(
            contest_id, request, user_id
        )


@pytest.mark.asyncio
async def test_assign_instructors_instructor_not_found(
    contest_service: "ContestService", mock_db, mock_contest
):
    """Test assigning non-existent instructor to contest."""
    user_id = mock_contest.created_by
    instructor_id = uuid4()
    request = InstructorManageRequest(instructor_ids=[instructor_id])

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        elif model == User:
            mock.filter.return_value.first.return_value = None  # User not found
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch("app.service.contest_service.ContestPermission.can_manage_contest"):
        with pytest.raises(UserNotFoundError):
            await contest_service.assign_instructors_to_contest(
                mock_contest.id, request, user_id
            )


@pytest.mark.asyncio
async def test_assign_instructors_already_assigned(
    contest_service: "ContestService", mock_db, mock_contest, mock_instructor
):
    """Test assigning instructor who is already assigned to contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])
    existing_assignment = MockContestInstructor(
        contest_id=mock_contest.id, instructor_id=mock_instructor.id
    )

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        elif model == User:
            mock.filter.return_value.first.return_value = mock_instructor
        elif model == ContestInstructor:
            mock.filter.return_value.first.return_value = existing_assignment
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch("app.service.contest_service.ContestPermission.can_manage_contest"):
        with pytest.raises(InstructorAlreadyAssignedError):
            await contest_service.assign_instructors_to_contest(
                mock_contest.id, request, user_id
            )


@pytest.mark.asyncio
async def test_assign_instructors_permission_denied(
    contest_service: "ContestService", mock_db, mock_contest, mock_instructor
):
    """Test assigning instructors without permission."""
    user_id = uuid4()  # Different user
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest",
        side_effect=PermissionDeniedError("Permission denied"),
    ):
        with pytest.raises(PermissionDeniedError):
            await contest_service.assign_instructors_to_contest(
                mock_contest.id, request, user_id
            )


@pytest.mark.asyncio
async def test_remove_instructors_from_contest_success(
    contest_service: "ContestService", mock_db, mock_contest, mock_instructor
):
    """Test successful removal of instructors from contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])
    existing_assignment = MockContestInstructor(
        contest_id=mock_contest.id, instructor_id=mock_instructor.id
    )

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        elif model == ContestInstructor:
            mock.filter.return_value.first.return_value = existing_assignment
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest"
    ) as mock_perm:
        await contest_service.remove_instructors_from_contest(
            mock_contest.id, request, user_id
        )
        mock_perm.assert_called_once()

    mock_db.delete.assert_called_once_with(existing_assignment)
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_remove_instructors_not_assigned(
    contest_service: "ContestService", mock_db, mock_contest, mock_instructor
):
    """Test removing instructor who is not assigned to contest."""
    user_id = mock_contest.created_by
    request = InstructorManageRequest(instructor_ids=[mock_instructor.id])

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        elif model == ContestInstructor:
            mock.filter.return_value.first.return_value = None  # No assignment
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch("app.service.contest_service.ContestPermission.can_manage_contest"):
        with pytest.raises(InstructorNotAssignedError):
            await contest_service.remove_instructors_from_contest(
                mock_contest.id, request, user_id
            )


@pytest.mark.asyncio
async def test_get_contest_instructors_success(
    contest_service: "ContestService",
    mock_db,
    mock_contest,
    mock_instructor,
    mock_creator,
):
    """Test getting instructors for a contest."""

    # Setup query mocks
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = mock_contest
        elif model == User:
            # Mock for instructor join query
            mock.join.return_value.filter.return_value.count.return_value = 1
            mock.join.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = [
                mock_instructor
            ]
            # Mock for creator query
            mock.filter.return_value.first.return_value = mock_creator
        return mock

    mock_db.query.side_effect = query_side_effect

    user_id = mock_contest.created_by  # Use creator as user for permission
    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest"
    ) as mock_perm:
        result = await contest_service.get_contest_instructors(mock_contest.id, user_id)
        mock_perm.assert_called_once()

    assert result.total == 1
    assert len(result.instructors) == 1
    assert result.instructors[0].id == mock_instructor.id
    assert result.creator is not None
    assert result.creator.id == mock_creator.id


@pytest.mark.asyncio
async def test_get_contest_instructors_contest_not_found(
    contest_service: "ContestService", mock_db
):
    """Test getting instructors for non-existent contest."""
    contest_id = uuid4()

    # Mock contest not found
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = None
        return mock

    mock_db.query.side_effect = query_side_effect

    contest_id = uuid4()
    user_id = uuid4()
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
