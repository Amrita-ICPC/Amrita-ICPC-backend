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


@pytest.fixture
def sample_contest_data():
    return ContestCreate(
        name="Test Contest",
        description="A test contest",
        image="http://example.com/image.png",
        is_public=True,
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=2),
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
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_create_contest(
    contest_service: "ContestService", mock_db, sample_contest_data, existing_contest
):
    """Test successful creation of a contest."""
    user_id = existing_contest.created_by

    # Mock refresh to update the instance with ID (simulation)
    def side_effect_refresh(instance):
        instance.id = existing_contest.id
        instance.created_at = existing_contest.created_at
        instance.updated_at = existing_contest.updated_at
        return None

    mock_db.refresh.side_effect = side_effect_refresh

    result = await contest_service.create_contest(sample_contest_data, user_id)

    assert result.id == existing_contest.id
    assert result.name == existing_contest.name
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_create_contest_exception_propagation(
    contest_service, mock_db, sample_contest_data, existing_contest
):
    """Test that exceptions during creation are propagated (allowing global rollback)."""
    user_id = existing_contest.created_by
    # Simulate error during flush or add
    mock_db.flush.side_effect = RuntimeError("DB Error")

    with pytest.raises(RuntimeError, match="DB Error"):
        await contest_service.create_contest(sample_contest_data, user_id)

    # No explicit rollback in service, so we don't assert it here.
    # We just ensure the exception bubbles up for global handler.


@pytest.mark.asyncio
async def test_get_contest_by_id_success(contest_service, mock_db, existing_contest):
    """Test retrieving a contest by ID successfully."""
    # Setup chain: db.query(Contest).filter(...).first() -> existing_contest
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = existing_contest

    result = await contest_service.get_contest_by_id(existing_contest.id)

    assert result.id == existing_contest.id
    mock_db.query.assert_called_with(Contest)


@pytest.mark.asyncio
async def test_get_contest_by_id_not_found(contest_service, mock_db):
    """Test retrieving a non-existent contest raises ContestNotFoundError."""
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = None
    contest_id = uuid4()

    with pytest.raises(ContestNotFoundError):
        await contest_service.get_contest_by_id(contest_id)


@pytest.mark.asyncio
async def test_get_all_contests(contest_service, mock_db, existing_contest):
    """Test retrieving all contests with pagination."""
    user_id = uuid4()

    # query(Contest).outerjoin().filter().distinct()
    # query(Contest).outerjoin().filter().distinct()
    mock_db.query.return_value.outerjoin.return_value.filter.return_value.distinct.return_value.count.return_value = 1
    mock_db.query.return_value.outerjoin.return_value.filter.return_value.distinct.return_value.offset.return_value.limit.return_value.all.return_value = [
        existing_contest
    ]

    total, contests = await contest_service.get_all_contests(user_id)

    assert total == 1
    assert len(contests) == 1
    assert contests[0].id == existing_contest.id
    mock_db.query.assert_called_with(Contest)


@pytest.mark.asyncio
async def test_update_contest_success_owner(contest_service, mock_db, existing_contest):
    """Test successful contest update by the owner."""

    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = existing_contest
        return mock

    mock_db.query.side_effect = query_side_effect

    update_data = ContestUpdate(name="Updated Name")
    user_id = existing_contest.created_by  # Owner

    # Mock permission check to pass
    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest"
    ) as mock_perm:
        result = await contest_service.update_contest(
            existing_contest.id, update_data, user_id
        )
        mock_perm.assert_called_once()

    assert result.name == "Updated Name"
    # existing_contest itself should be mutated
    assert existing_contest.name == "Updated Name"
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_with(existing_contest)


@pytest.mark.asyncio
async def test_update_contest_permission_denied(
    contest_service, mock_db, existing_contest
):
    """Test that updating a contest without permission raises PermissionDeniedError."""
    user_id = uuid4()  # Not owner

    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = existing_contest
        return mock

    mock_db.query.side_effect = query_side_effect

    update_data = ContestUpdate(name="Updated Name")

    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest",
        side_effect=PermissionDeniedError("Denied"),
    ):
        with pytest.raises(PermissionDeniedError):
            await contest_service.update_contest(
                existing_contest.id, update_data, user_id
            )


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
async def test_delete_contest_success(contest_service, mock_db, existing_contest):
    """Test successful contest deletion."""

    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = existing_contest
        return mock

    mock_db.query.side_effect = query_side_effect

    user_id = existing_contest.created_by

    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest"
    ) as mock_perm:
        result = await contest_service.delete_contest(existing_contest.id, user_id)
        mock_perm.assert_called_once()

    assert result.id == existing_contest.id
    mock_db.delete.assert_called_once_with(existing_contest)
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_contest_permission_denied(
    contest_service, mock_db, existing_contest
):
    """Test that deleting a contest without permission raises PermissionDeniedError."""
    user_id = uuid4()  # Not owner

    def query_side_effect(model):
        mock = MagicMock()
        if model == Contest:
            mock.filter.return_value.first.return_value = existing_contest
        return mock

    mock_db.query.side_effect = query_side_effect

    with patch(
        "app.service.contest_service.ContestPermission.can_manage_contest",
        side_effect=PermissionDeniedError("Denied"),
    ):
        with pytest.raises(PermissionDeniedError):
            await contest_service.delete_contest(existing_contest.id, user_id)
