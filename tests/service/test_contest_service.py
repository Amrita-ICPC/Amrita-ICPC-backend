import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from app.service.contest_service import ContestService
from app.repositories.contest_repository import ContestRepository
from app.schema.contest import ContestCreate, ContestUpdate, ContestResponse
from app.exceptions.contest import ContestNotFoundError, InvalidContestError
from app.exceptions.auth import PermissionDeniedError
from copy import deepcopy

@pytest.fixture
def mock_repo():
    return MagicMock(spec=ContestRepository)

@pytest.fixture
def contest_service(mock_repo):
    # Patch the cache decorators to avoid redis connection issues
    with patch("app.core.cache.decorators.cache_get", side_effect=lambda **kwargs: lambda func: func), \
         patch("app.core.cache.decorators.cache_set", side_effect=lambda **kwargs: lambda func: func), \
         patch("app.core.cache.decorators.cache_delete", side_effect=lambda **kwargs: lambda func: func):
        service = ContestService(mock_repo)
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
        image=str(sample_contest_data.image), # Pydantic URL string
        is_public=sample_contest_data.is_public,
        start_time=sample_contest_data.start_time,
        end_time=sample_contest_data.end_time,
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

@pytest.mark.asyncio
async def test_create_contest(contest_service:ContestService, mock_repo, sample_contest_data, existing_contest):
    user_id = existing_contest.created_by
    mock_repo.create.return_value = existing_contest

    result = await contest_service.create_contest(sample_contest_data, user_id)

    assert result.id == existing_contest.id
    assert result.name == existing_contest.name
    mock_repo.create.assert_called_once_with(sample_contest_data, user_id)


@pytest.mark.asyncio
async def test_get_contest_by_id_success(contest_service, mock_repo, existing_contest):
    mock_repo.get_by_id.return_value = existing_contest

    result = await contest_service.get_contest_by_id(existing_contest.id)

    assert result.id == existing_contest.id
    mock_repo.get_by_id.assert_called_once_with(existing_contest.id)

@pytest.mark.asyncio
async def test_get_contest_by_id_not_found(contest_service, mock_repo):
    mock_repo.get_by_id.return_value = None
    contest_id = uuid4()

    with pytest.raises(ContestNotFoundError):
        await contest_service.get_contest_by_id(contest_id)

@pytest.mark.asyncio
async def test_get_all_contests(contest_service, mock_repo, existing_contest):
    user_id = uuid4()
    mock_repo.get_all.return_value = (1, [existing_contest])

    total, contests = await contest_service.get_all_contests(user_id)

    assert total == 1
    assert len(contests) == 1
    assert contests[0].id == existing_contest.id
    mock_repo.get_all.assert_called_once_with(user_id, 0, 100)

@pytest.mark.asyncio
async def test_update_contest_success_owner(contest_service, mock_repo, existing_contest):
    mock_repo.get_by_id.return_value = existing_contest
    update_data = ContestUpdate(name="Updated Name")
    user_id = existing_contest.created_by # Owner
    
    updated_contest_obj = deepcopy(existing_contest)
    updated_contest_obj.name = "Updated Name"
    mock_repo.update.return_value = updated_contest_obj

    result = await contest_service.update_contest(existing_contest.id, update_data, user_id)

    assert result.name == "Updated Name"
    mock_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_contest_permission_denied(contest_service, mock_repo, existing_contest):
    mock_repo.get_by_id.return_value = existing_contest
    update_data = ContestUpdate(name="Updated Name")
    other_user_id = uuid4()
    mock_repo.is_instructor.return_value = False

    with pytest.raises(PermissionDeniedError):
        await contest_service.update_contest(existing_contest.id, update_data, other_user_id)

@pytest.mark.asyncio
async def test_update_contest_invalid_dates(contest_service, mock_repo, existing_contest):
    mock_repo.get_by_id.return_value = existing_contest
    user_id = existing_contest.created_by
    # End time before start time
    update_data = ContestUpdate(
        start_time=datetime.now() + timedelta(hours=5),
        end_time=datetime.now() + timedelta(hours=1),
    )

    with pytest.raises(InvalidContestError):
        await contest_service.update_contest(existing_contest.id, update_data, user_id)

@pytest.mark.asyncio
async def test_delete_contest_success(contest_service, mock_repo, existing_contest):
    mock_repo.get_by_id.return_value = existing_contest
    user_id = existing_contest.created_by

    result = await contest_service.delete_contest(existing_contest.id, user_id)

    assert result.id == existing_contest.id
    mock_repo.delete.assert_called_once_with(existing_contest)

@pytest.mark.asyncio
async def test_delete_contest_permission_denied(contest_service, mock_repo, existing_contest):
    mock_repo.get_by_id.return_value = existing_contest
    other_user_id = uuid4()
    mock_repo.is_instructor.return_value = False

    with pytest.raises(PermissionDeniedError):
        await contest_service.delete_contest(existing_contest.id, other_user_id)
