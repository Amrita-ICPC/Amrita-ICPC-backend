import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.guards.team_student import TeamStudentGuard
from app.exceptions.student.teams import (
    TeamLeaderAccessDeniedError,
    TeamMemberAccessDeniedError,
)
from app.models.team import Team


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock database AsyncSession."""
    return AsyncMock()


@pytest.fixture
def team_student_guard(mock_db: AsyncMock) -> TeamStudentGuard:
    """Initialize TeamStudentGuard with mocked DB session."""
    return TeamStudentGuard(db=mock_db)


def test_check_is_leader_success(team_student_guard: TeamStudentGuard):
    """Test that check_is_leader passes silently when student is indeed the leader."""
    user_id = uuid.uuid4()
    mock_team = MagicMock(spec=Team)
    mock_team.id = uuid.uuid4()
    mock_team.leader_id = user_id

    # Should not raise any error
    team_student_guard.check_is_leader(user_id=user_id, team=mock_team)


def test_check_is_leader_raises_exception(team_student_guard: TeamStudentGuard):
    """Test that check_is_leader raises TeamLeaderAccessDeniedError when student is not the leader."""
    user_id = uuid.uuid4()
    leader_id = uuid.uuid4()
    mock_team = MagicMock(spec=Team)
    mock_team.id = uuid.uuid4()
    mock_team.leader_id = leader_id

    with pytest.raises(TeamLeaderAccessDeniedError) as excinfo:
        team_student_guard.check_is_leader(user_id=user_id, team=mock_team)

    assert str(mock_team.id) in str(excinfo.value)
    assert str(user_id) in str(excinfo.value)


@pytest.mark.asyncio
async def test_check_is_member_success(
    team_student_guard: TeamStudentGuard, mock_db: AsyncMock
):
    """Test that check_is_member passes silently when the user is a member."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Mock DB execution result to return True (member exists)
    mock_result = MagicMock()
    mock_result.scalar.return_value = True
    mock_db.execute.return_value = mock_result

    # Should not raise any exception
    await team_student_guard.check_is_member(team_id=team_id, user_id=user_id)

    # Verify query execution
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_check_is_member_raises_exception(
    team_student_guard: TeamStudentGuard, mock_db: AsyncMock
):
    """Test that check_is_member raises TeamMemberAccessDeniedError when the user is not a member."""
    team_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Mock DB execution result to return False (member does not exist)
    mock_result = MagicMock()
    mock_result.scalar.return_value = False
    mock_db.execute.return_value = mock_result

    with pytest.raises(TeamMemberAccessDeniedError) as excinfo:
        await team_student_guard.check_is_member(team_id=team_id, user_id=user_id)

    assert str(team_id) in str(excinfo.value)
    assert str(user_id) in str(excinfo.value)
    assert mock_db.execute.called
