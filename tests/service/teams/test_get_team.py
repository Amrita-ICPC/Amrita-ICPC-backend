"""Comprehensive tests for TeamService team retrieval methods.

This module tests the refactored team retrieval operations using the repository,
guard, and validator patterns. Tests are organized by method and validation concern.

Methods Under Test:
    - get_contest_teams: Retrieve teams with filtering, search, and pagination
    - get_team_by_id: Retrieve a specific team by ID with permission checks

Test Organization:
    Each method has dedicated test classes covering:
    - Success scenarios with various parameter combinations
    - Contest existence validation
    - Permission validation via TeamOperationGuard
    - Team existence validation
    - Repository contract verification
    - Execution order validation

Test Strategy:
    - Mock repository, guard, and validator dependencies
    - Verify correct data flow between service and repository
    - Ensure proper exception handling and error propagation
    - Validate permission checks occur before data access
    - Confirm response mapping from domain objects to DTOs

All tests follow the existing test structure established in test_create_team.py
and test_update_team.py for consistency across the test suite.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import TeamNotFoundError
from app.repositories.team import PaginationParams, TeamFilters
from app.schema.team import ContestTeamResponse
from app.utils.enums import TeamStatus


class TestGetContestTeamsSuccess:
    """Test successful team retrieval scenarios."""

    @pytest.mark.asyncio
    async def test_returns_tuple_with_count_and_teams(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that get_contest_teams returns (total_count, list[ContestTeamResponse])."""
        mock_teams = [MagicMock(), MagicMock(), MagicMock()]
        mock_result = MagicMock(total=3, items=mock_teams)
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        with patch.object(
            ContestTeamResponse, "from_contest_team", side_effect=lambda x: x
        ):
            total, teams = await team_service.get_contest_teams(contest_id, user_id)

        assert total == 3
        assert len(teams) == 3

    @pytest.mark.asyncio
    async def test_empty_results_returns_zero_count(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that empty results return (0, [])."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        total, teams = await team_service.get_contest_teams(contest_id, user_id)

        assert total == 0
        assert teams == []

    @pytest.mark.asyncio
    async def test_with_search_term_filters_correctly(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that search_term parameter is passed to repository."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(contest_id, user_id, search_term="Alpha")

        call_args = mock_repository.get_contest_teams.call_args[0]
        filters = call_args[1]
        assert filters.search_term == "Alpha"

    @pytest.mark.asyncio
    async def test_with_status_filter_returns_only_matching(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that status filter is passed to repository."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(
            contest_id, user_id, status=TeamStatus.CONFIRMED
        )

        call_args = mock_repository.get_contest_teams.call_args[0]
        filters = call_args[1]
        assert filters.status == TeamStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_with_pagination_returns_correct_page(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that pagination parameters are passed correctly."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(contest_id, user_id, skip=10, limit=20)

        call_args = mock_repository.get_contest_teams.call_args[0]
        pagination = call_args[2]
        assert pagination.skip == 10
        assert pagination.limit == 20

    @pytest.mark.asyncio
    async def test_combined_filters_work_together(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that search, status, and pagination work together."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(
            contest_id,
            user_id,
            search_term="Team",
            status=TeamStatus.DRAFT,
            skip=5,
            limit=15,
        )

        call_args = mock_repository.get_contest_teams.call_args[0]
        filters = call_args[1]
        pagination = call_args[2]

        assert filters.search_term == "Team"
        assert filters.status == TeamStatus.DRAFT
        assert pagination.skip == 5
        assert pagination.limit == 15


class TestGetContestTeamsContestValidation:
    """Test contest existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.get_contest_teams(contest_id, user_id)

        mock_guard.check_read_team.assert_not_called()
        mock_repository.get_contest_teams.assert_not_called()


class TestGetContestTeamsPermissions:
    """Test permission validation."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_read_permission(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_read_team.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.get_contest_teams(contest_id, user_id)

        mock_repository.get_contest_teams.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(contest_id, user_id)

        mock_guard.check_read_team.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )


class TestGetContestTeamsRepositoryContract:
    """Test the interface contract between service and repository."""

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_filters(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that TeamFilters object is created correctly."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(
            contest_id, user_id, search_term="Alpha", status=TeamStatus.CONFIRMED
        )

        call_args = mock_repository.get_contest_teams.call_args[0]
        assert call_args[0] == contest_id
        assert isinstance(call_args[1], TeamFilters)
        assert call_args[1].search_term == "Alpha"
        assert call_args[1].status == TeamStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_pagination(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that PaginationParams object is created correctly."""
        mock_result = MagicMock(total=0, items=[])
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        await team_service.get_contest_teams(contest_id, user_id, skip=20, limit=50)

        call_args = mock_repository.get_contest_teams.call_args[0]
        assert isinstance(call_args[2], PaginationParams)
        assert call_args[2].skip == 20
        assert call_args[2].limit == 50

    @pytest.mark.asyncio
    async def test_response_mapping_from_domain_objects(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that each ContestTeam is mapped to ContestTeamResponse."""
        mock_teams = [MagicMock(), MagicMock()]
        mock_result = MagicMock(total=2, items=mock_teams)
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_contest_teams.return_value = mock_result

        with patch.object(
            ContestTeamResponse, "from_contest_team"
        ) as mock_from_contest_team:
            mock_from_contest_team.side_effect = lambda x: MagicMock()

            _, teams = await team_service.get_contest_teams(contest_id, user_id)

            assert mock_from_contest_team.call_count == 2
            assert len(teams) == 2


class TestGetTeamByIdSuccess:
    """Test successful team retrieval by ID."""

    @pytest.mark.asyncio
    async def test_returns_contest_team_response(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        mock_contest_team_response,
        contest_id,
        user_id,
    ):
        """Test that get_team_by_id returns ContestTeamResponse."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_by_id.return_value = mock_contest_team

        with patch.object(
            ContestTeamResponse,
            "from_contest_team",
            return_value=mock_contest_team_response,
        ):
            result = await team_service.get_team_by_id(contest_id, team_id, user_id)

        assert result == mock_contest_team_response


class TestGetTeamByIdContestValidation:
    """Test contest existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.get_team_by_id(contest_id, team_id, user_id)

        mock_guard.check_read_team.assert_not_called()
        mock_repository.get_team_by_id.assert_not_called()


class TestGetTeamByIdPermissions:
    """Test permission validation."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_read_permission(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_read_team.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.get_team_by_id(contest_id, team_id, user_id)

        mock_repository.get_team_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_by_id.return_value = mock_contest_team

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.get_team_by_id(contest_id, team_id, user_id)

        mock_guard.check_read_team.assert_called_once_with(
            user_id=user_id, contest=mock_contest
        )


class TestGetTeamByIdTeamValidation:
    """Test team existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(
        self,
        team_service,
        mock_repository,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that TeamNotFoundError is raised when team doesn't exist."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_by_id.side_effect = TeamNotFoundError(
            str(team_id), str(contest_id)
        )

        with pytest.raises(TeamNotFoundError):
            await team_service.get_team_by_id(contest_id, team_id, user_id)


class TestGetTeamByIdRepositoryContract:
    """Test the interface contract between service and repository."""

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_ids(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that repository is called with correct contest_id and team_id."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_by_id.return_value = mock_contest_team

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.get_team_by_id(contest_id, team_id, user_id)

        mock_repository.get_team_by_id.assert_called_once_with(contest_id, team_id)

    @pytest.mark.asyncio
    async def test_response_mapping_from_domain_object(
        self,
        team_service,
        mock_repository,
        mock_contest,
        mock_contest_team,
        contest_id,
        user_id,
    ):
        """Test that ContestTeam is mapped to ContestTeamResponse."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_repository.get_team_by_id.return_value = mock_contest_team

        with patch.object(
            ContestTeamResponse, "from_contest_team"
        ) as mock_from_contest_team:
            await team_service.get_team_by_id(contest_id, team_id, user_id)

            mock_from_contest_team.assert_called_once_with(mock_contest_team)


class TestGetTeamByIdExecutionOrder:
    """Test the correct execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_contest_validated_before_guard(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        user_id,
    ):
        """Test that contest validation occurs before permission checks."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.get_team_by_id(contest_id, team_id, user_id)

        mock_guard.check_read_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_validated_before_team_fetch(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        contest_id,
        user_id,
    ):
        """Test that permission check occurs before team fetch."""
        team_id = uuid4()
        mock_repository.get_contest_or_raise.return_value = mock_contest
        mock_guard.check_read_team.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.get_team_by_id(contest_id, team_id, user_id)

        mock_repository.get_team_by_id.assert_not_called()
