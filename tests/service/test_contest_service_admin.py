from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    pass


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


@pytest.fixture
def existing_contest():
    contest_id = uuid4()
    creator_id = uuid4()
    return MockContest(
        id=contest_id,
        name="Test Contest",
        description="A test contest",
        image="http://example.com/image.png",
        is_public=True,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc) + timedelta(hours=2),
        registration_start=datetime.now(timezone.utc) - timedelta(hours=1),
        registration_end=datetime.now(timezone.utc),
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
async def test_get_all_contests_admin(contest_service, mock_db, existing_contest):
    """Test retrieving all contests for admin user."""

    admin_id = uuid4()

    # Mock is_admin to return True
    with patch("app.service.contest_service.is_admin", return_value=True):
        # Setup contest query
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.distinct.return_value.count.return_value = 1
        mock_query.filter.return_value.distinct.return_value.offset.return_value.limit.return_value.all.return_value = [
            existing_contest
        ]

        total, contests = await contest_service.get_all_contests(admin_id)

    assert total == 1
    assert len(contests) == 1
    assert contests[0].id == existing_contest.id


@pytest.mark.asyncio
async def test_get_soft_deleted_contests_admin(
    contest_service, mock_db, existing_contest
):
    """Test retrieving soft-deleted contests for admin user."""

    admin_id = uuid4()
    existing_contest.is_deleted = True

    # Mock is_admin to return True
    with patch("app.service.contest_service.is_admin", return_value=True):
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.distinct.return_value.count.return_value = 1
        mock_query.filter.return_value.distinct.return_value.offset.return_value.limit.return_value.all.return_value = [
            existing_contest
        ]

        total, contests = await contest_service.get_soft_deleted_contests(admin_id)

    assert total == 1
    assert len(contests) == 1
    assert contests[0].id == existing_contest.id
