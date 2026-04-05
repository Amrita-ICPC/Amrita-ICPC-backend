"""Global test configuration and shared fixtures for all tests.

This module provides common fixtures that can be used across all test modules
in the project. It includes basic ID generators, database mocks, and common
test objects that are used throughout the test suite.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.contest import Contest
from app.utils.enums import TeamApprovalMode


@pytest.fixture
def mock_db():
    """Mock database session for service tests.

    Returns:
        MagicMock: Mock SQLAlchemy session object
    """
    return MagicMock(spec=Session)


@pytest.fixture
def contest_id():
    """Generate a unique contest ID for each test.

    Returns:
        UUID: Random UUID for contest identification
    """
    return uuid4()


@pytest.fixture
def user_id():
    """Generate a unique user ID for each test.

    Returns:
        UUID: Random UUID for user identification
    """
    return uuid4()


@pytest.fixture
def member_ids():
    """Generate a list of member IDs for team testing.

    Returns:
        list[UUID]: List of 2 unique UUIDs representing team members
    """
    return [uuid4(), uuid4()]


@pytest.fixture
def leader_id(member_ids):
    """Provide a leader ID that is always part of the team members.

    Args:
        member_ids: List of member UUIDs from member_ids fixture

    Returns:
        UUID: First member ID, designated as the team leader
    """
    return member_ids[0]


@pytest.fixture
def team_id():
    """Generate a unique team ID for each test.

    Returns:
        UUID: Random UUID for team identification
    """
    return uuid4()


@pytest.fixture
def mock_contest():
    """Create a mock contest with standard configuration.

    Returns:
        MagicMock: Mock Contest object with typical attributes set
    """
    contest = MagicMock(spec=Contest)
    contest.id = uuid4()
    contest.min_team_size = 2
    contest.max_team_size = 5
    contest.team_approval_mode = TeamApprovalMode.AUTO_APPROVE
    return contest
