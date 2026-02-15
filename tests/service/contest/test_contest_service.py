from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError

# Models imported to ensure SQLAlchemy mapper registry is populated
from app.models.contest import Contest
from app.schema.contest import ContestCreate, ContestUpdate

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


@pytest.fixture
def sample_contest_data():
    return ContestCreate(
        name="Test Contest",
        description="A test contest",
        image="http://example.com/image.png",
        is_public=True,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc) + timedelta(hours=2),
        registration_start=datetime.now(timezone.utc) - timedelta(hours=1),
        registration_end=datetime.now(timezone.utc),
    )


class MockContest:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def existing_contest(sample_contest_data):
    contest_id = uuid4()
    creator_id = uuid4()
    return MockContest(
        id=contest_id,
        name=sample_contest_data.name,
        description=sample_contest_data.description,
        image=str(sample_contest_data.image),  # Pydantic URL string
        is_public=sample_contest_data.is_public,
        start_time=sample_contest_data.start_time,
        end_time=sample_contest_data.end_time,
        registration_start=sample_contest_data.registration_start,
        registration_end=sample_contest_data.registration_end,
        max_teams=None,
        min_team_size=1,
        max_team_size=1,
        rules=None,
        scoring_type="AUTO",
        status="DRAFT",
        published_at=None,
        show_leaderboard=False,
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        updated_by=None,
        is_deleted=False,
        deleted_at=None,
        deleted_by=None,
    )


@pytest.mark.asyncio
async def test_create_contest(
    contest_service: "ContestService",
    mock_contest_repository,
    sample_contest_data,
    existing_contest,
):
    """Test successful creation of a contest."""
    user_id = existing_contest.created_by

    # Mock repository create_contest to return existing_contest
    mock_contest_repository.create_contest.return_value = existing_contest

    result = await contest_service.create_contest(sample_contest_data, user_id)

    assert result.id == existing_contest.id
    assert result.name == existing_contest.name
    mock_contest_repository.create_contest.assert_called_once()


@pytest.mark.asyncio
async def test_create_contest_exception_propagation(
    contest_service, mock_contest_repository, sample_contest_data, existing_contest
):
    """Test that exceptions during creation are propagated (allowing global rollback)."""
    user_id = existing_contest.created_by
    # Simulate error during repository operation
    mock_contest_repository.create_contest.side_effect = RuntimeError("DB Error")

    with pytest.raises(RuntimeError, match="DB Error"):
        await contest_service.create_contest(sample_contest_data, user_id)

    # No explicit rollback in service, so we don't assert it here.
    # We just ensure the exception bubbles up for global handler.


@pytest.mark.asyncio
async def test_get_contest_by_id_success(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test retrieving a contest by ID successfully."""
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    result = await contest_service.get_contest_by_id(
        existing_contest.id, existing_contest.created_by
    )

    assert result.id == existing_contest.id
    mock_contest_repository.get_contest_or_raise.assert_called_once_with(
        existing_contest.id
    )
    mock_guard.check_read_contest.assert_called_once()


@pytest.mark.asyncio
async def test_get_contest_by_id_not_found(contest_service, mock_contest_repository):
    """Test retrieving a non-existent contest raises ContestNotFoundError."""
    contest_id = uuid4()
    # Mock repository to raise ContestNotFoundError
    mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
        contest_id
    )

    with pytest.raises(ContestNotFoundError):
        await contest_service.get_contest_by_id(contest_id, uuid4())


@pytest.mark.asyncio
async def test_get_all_contests(
    contest_service, mock_contest_repository, mock_user_repository, existing_contest
):
    """Test retrieving all contests with pagination."""
    user_id = uuid4()

    # Mock repository to return paginated result
    from app.repositories.dto import PaginatedResult

    mock_contest_repository.get_contests_with_filters.return_value = PaginatedResult(
        total=1, items=[existing_contest]
    )

    # Mock user repository to return non-admin user
    from app.utils.enums import UserRole

    mock_user = MagicMock()
    mock_user.role = UserRole.student
    mock_user_repository.get_user_by_id.return_value = mock_user

    total, contests = await contest_service.get_all_contests(user_id)

    assert total == 1
    assert len(contests) == 1
    assert contests[0].id == existing_contest.id
    mock_contest_repository.get_contests_with_filters.assert_called_once()


@pytest.mark.asyncio
async def test_update_contest_success_owner(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test successful contest update by the owner."""
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    # Create a copy with updated name
    updated_contest = MockContest(**existing_contest.__dict__)
    updated_contest.name = "Updated Name"
    mock_contest_repository.update_contest.return_value = updated_contest

    update_data = ContestUpdate(name="Updated Name")
    user_id = existing_contest.created_by  # Owner

    result = await contest_service.update_contest(
        existing_contest.id, update_data, user_id
    )

    assert result.name == "Updated Name"
    mock_contest_repository.get_contest_or_raise.assert_called_once_with(
        existing_contest.id
    )
    mock_guard.check_manage_contest.assert_called_once()
    mock_contest_repository.update_contest.assert_called_once()


@pytest.mark.asyncio
async def test_update_contest_permission_denied(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test update fails when user lacks permission."""
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    # Mock guard to raise PermissionDeniedError
    mock_guard.check_manage_contest.side_effect = PermissionDeniedError(
        "User does not have permission"
    )

    update_data = ContestUpdate(name="Updated Name")
    user_id = uuid4()  # Different user

    with pytest.raises(PermissionDeniedError):
        await contest_service.update_contest(existing_contest.id, update_data, user_id)


@pytest.mark.asyncio
async def test_update_contest_invalid_dates(
    contest_service: "ContestService", mock_db, existing_contest
):
    """Test that updating with invalid dates (end < start) raises ValidationError via Pydantic."""

    # Setup get by id (owner)
    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = existing_contest
        return mock

    mock_db.query.side_effect = query_side_effect

    # End time before start time
    # The model now validates this, so it raises ValidationError on instantiation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContestUpdate(
            start_time=datetime.now() + timedelta(hours=5),
            end_time=datetime.now() + timedelta(hours=1),
        )


@pytest.mark.asyncio
async def test_delete_contest_success(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test successful deletion of a contest."""
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    result = await contest_service.delete_contest(
        existing_contest.id, existing_contest.created_by
    )

    assert result.id == existing_contest.id
    mock_contest_repository.get_contest_or_raise.assert_called_once_with(
        existing_contest.id
    )
    mock_guard.check_manage_contest.assert_called_once()
    mock_contest_repository.delete_contest.assert_called_once_with(existing_contest)


@pytest.mark.asyncio
async def test_delete_contest_permission_denied(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test delete fails when user lacks permission."""
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    # Mock guard to raise PermissionDeniedError
    mock_guard.check_manage_contest.side_effect = PermissionDeniedError(
        "User does not have permission"
    )

    user_id = uuid4()  # Different user

    with pytest.raises(PermissionDeniedError):
        await contest_service.delete_contest(existing_contest.id, user_id)


@pytest.mark.asyncio
async def test_publish_contest_success(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test successful publishing of a contest."""
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    await contest_service.publish_contest(
        existing_contest.id, existing_contest.created_by
    )

    mock_contest_repository.get_contest_or_raise.assert_called_once_with(
        existing_contest.id
    )
    mock_guard.check_manage_contest.assert_called_once()
    mock_contest_repository.publish_contest.assert_called_once_with(
        existing_contest, existing_contest.created_by
    )


@pytest.mark.asyncio
async def test_soft_delete_contest_success(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test successful soft deletion of a contest."""
    existing_contest.is_deleted = False
    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    await contest_service.soft_delete_contest(
        existing_contest.id, existing_contest.created_by
    )

    mock_contest_repository.get_contest_or_raise.assert_called_once_with(
        existing_contest.id
    )
    mock_guard.check_manage_contest.assert_called_once()
    mock_contest_repository.soft_delete_contest.assert_called_once_with(
        existing_contest, existing_contest.created_by
    )


@pytest.mark.asyncio
async def test_get_soft_deleted_contest(contest_service, mock_db, existing_contest):
    """Test that retrieving a soft-deleted contest raises ContestNotFoundError."""
    existing_contest.is_deleted = True

    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = existing_contest

    with pytest.raises(ContestNotFoundError):
        await contest_service.get_contest_by_id(existing_contest.id, uuid4())


@pytest.mark.asyncio
async def test_restore_contest_success(
    contest_service, mock_contest_repository, mock_guard, existing_contest
):
    """Test successful restoration of a soft-deleted contest."""
    existing_contest.is_deleted = True
    existing_contest.deleted_at = datetime.now(timezone.utc)
    existing_contest.deleted_by = existing_contest.created_by

    # Mock repository to return existing_contest
    mock_contest_repository.get_contest_or_raise.return_value = existing_contest

    # Create restored version
    restored_contest = MockContest(**existing_contest.__dict__)
    restored_contest.is_deleted = False
    restored_contest.deleted_at = None
    restored_contest.deleted_by = None
    mock_contest_repository.restore_contest.return_value = restored_contest

    result = await contest_service.restore_contest(
        existing_contest.id, existing_contest.created_by
    )

    # Check that result has the correct contest ID
    assert result.id == existing_contest.id
    mock_contest_repository.get_contest_or_raise.assert_called_once_with(
        existing_contest.id
    )
    mock_guard.check_manage_contest.assert_called_once()
    mock_contest_repository.restore_contest.assert_called_once_with(existing_contest)


@pytest.mark.asyncio
async def test_get_soft_deleted_contests(
    contest_service, mock_contest_repository, mock_user_repository, existing_contest
):
    """Test retrieving soft-deleted contests."""
    existing_contest.is_deleted = True
    user_id = existing_contest.created_by

    # Mock repository to return paginated result
    from app.repositories.dto import PaginatedResult

    mock_contest_repository.get_soft_deleted_contests.return_value = PaginatedResult(
        total=1, items=[existing_contest]
    )

    # Mock user repository to return non-admin user
    from app.utils.enums import UserRole

    mock_user = MagicMock()
    mock_user.role = UserRole.student
    mock_user_repository.get_user_or_raise.return_value = mock_user

    total, contests = await contest_service.get_soft_deleted_contests(user_id)

    assert total == 1
    assert len(contests) == 1
    assert contests[0].id == existing_contest.id
    # Note: is_deleted is not exposed in response schema
    mock_contest_repository.get_soft_deleted_contests.assert_called_once()
