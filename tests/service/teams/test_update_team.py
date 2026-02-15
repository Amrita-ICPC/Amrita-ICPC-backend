from unittest.mock import MagicMock, patch

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError
from app.exceptions.team import (
    InvalidTeamSizeError,
    TeamAlreadyExistsError,
    TeamNotFoundError,
)
from app.repositories.team import UpdateTeamData
from app.schema.team import ContestTeamResponse, TeamUpdate
from app.utils.enums import TeamStatus

# ── Fixtures unique to update_team ───────────────────────────────────────────


@pytest.fixture
def team_update_data():
    """Default update — only name changes, everything else None."""
    return TeamUpdate(
        name="Updated Team Name",
        description=None,
        logo=None,
        status=None,
    )


@pytest.fixture
def confirm_update_data():
    """Status transition from DRAFT to CONFIRMED."""
    return TeamUpdate(
        name=None,
        description=None,
        logo=None,
        status=TeamStatus.CONFIRMED,
    )


class TestUpdateTeamSuccess:
    @pytest.mark.asyncio
    async def test_returns_contest_team_response(
        self,
        team_service,
        mock_repository,
        mock_contest_team_response,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN all validations pass
        WHEN update_team is called
        THEN returns ContestTeamResponse
        """
        # Arrange
        mock_repository.find_team_by_name.return_value = None
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(
            ContestTeamResponse,
            "from_contest_team",
            return_value=mock_contest_team_response,
        ):
            # Act
            result = await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        # Assert
        assert result == mock_contest_team_response

    @pytest.mark.asyncio
    async def test_update_only_description_succeeds(
        self,
        team_service,
        mock_repository,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        user_id,
    ):
        """
        GIVEN only description is provided
        WHEN update_team is called
        THEN succeeds — partial update works
        """
        # Arrange
        desc_only_update = TeamUpdate(
            name=None,
            description="New description",
            logo=None,
            status=None,
        )
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, desc_only_update, user_id
            )

    @pytest.mark.asyncio
    async def test_same_name_skips_uniqueness_check(
        self,
        team_service,
        mock_repository,
        mock_contest_team,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        user_id,
    ):
        """
        GIVEN name in update is same as current team name
        WHEN update_team is called
        THEN find_team_by_name never called
        """
        # Arrange — use same name as mock_team
        same_name_update = TeamUpdate(
            name=mock_contest_team.team.name,  # ← same name
            description=None,
            logo=None,
            status=None,
        )
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, same_name_update, user_id
            )

        # Assert
        mock_repository.find_team_by_name.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_name_skips_uniqueness_check(
        self,
        team_service,
        mock_repository,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        user_id,
    ):
        """
        GIVEN name is None in update
        WHEN update_team is called
        THEN find_team_by_name never called
        """
        # Arrange
        none_name_update = TeamUpdate(
            name=None,
            description="New description",
            logo=None,
            status=None,
        )
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, none_name_update, user_id
            )

        # Assert
        mock_repository.find_team_by_name.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_status_skips_size_check(
        self,
        team_service,
        mock_repository,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,  # ← status is None
        user_id,
    ):
        """
        GIVEN status is None in update
        WHEN update_team is called
        THEN size check never runs
        """
        # Arrange
        mock_repository.find_team_by_name.return_value = None
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        # Assert
        mock_repository.get_team_members_count_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_confirmed_skips_size_check(
        self,
        team_service,
        mock_repository,
        mock_contest_team,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        confirm_update_data,
        user_id,
    ):
        """
        GIVEN team is already CONFIRMED
        WHEN update_team called with CONFIRMED status
        THEN size check never runs — not a transition
        """
        # Arrange — override status to already confirmed
        mock_contest_team.team_status = TeamStatus.CONFIRMED
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, confirm_update_data, user_id
            )

        # Assert
        mock_repository.get_team_members_count_or_raise.assert_not_called()


class TestUpdateTeamContestValidation:
    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN contest does not exist
        WHEN update_team is called
        THEN ContestNotFoundError raised
        AND guard never called
        """
        # Arrange — no setup_valid_contest, we WANT it to fail
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        # Act & Assert
        with pytest.raises(ContestNotFoundError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_guard.check_update_team.assert_not_called()


class TestUpdateTeamPermissions:
    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        team_service,
        mock_guard,
        mock_repository,
        setup_valid_contest,  # ← contest passes, guard fails
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN user lacks permission
        WHEN update_team is called
        THEN PermissionDeniedError raised
        AND get_contest_team_or_raise never called
        """
        # Arrange
        mock_guard.check_update_team.side_effect = PermissionDeniedError()

        # Act & Assert
        with pytest.raises(PermissionDeniedError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_repository.get_contest_team_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_guard,
        mock_contest,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN contest exists
        WHEN update_team is called
        THEN guard called with correct user_id and contest
        """
        # Arrange
        mock_repository.find_team_by_name.return_value = None
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        # Assert exact args
        mock_guard.check_update_team.assert_called_once_with(
            user_id=user_id,
            contest=mock_contest,
        )


class TestUpdateTeamTeamValidation:
    @pytest.mark.asyncio
    async def test_raises_when_team_not_found(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest,  # ← contest passes, team fails
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN team not found in contest
        WHEN update_team is called
        THEN TeamNotFoundError raised
        AND validator never called
        """
        # Arrange
        mock_repository.get_contest_team_or_raise.side_effect = TeamNotFoundError(
            str(team_id), str(contest_id)
        )

        # Act & Assert
        with pytest.raises(TeamNotFoundError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_validator.validate_name_unique.assert_not_called()


class TestUpdateTeamNameValidation:
    @pytest.mark.asyncio
    async def test_raises_when_name_already_exists(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN name conflicts with existing team
        WHEN update_team is called
        THEN TeamAlreadyExistsError raised
        AND repository.update_team never called
        """
        # Arrange
        mock_repository.find_team_by_name.return_value = MagicMock()
        mock_validator.validate_name_unique.side_effect = TeamAlreadyExistsError(
            team_update_data.name, str(contest_id)
        )

        # Act & Assert
        with pytest.raises(TeamAlreadyExistsError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_repository.update_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_name_unique_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN name is changing
        WHEN update_team is called
        THEN validate_name_unique called with correct args
        """
        # Arrange
        existing = MagicMock()
        mock_repository.find_team_by_name.return_value = existing
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        # Assert
        mock_validator.validate_name_unique.assert_called_once_with(
            contest_id,
            team_update_data.name,
            existing,
        )


class TestUpdateTeamSizeValidation:
    @pytest.mark.asyncio
    async def test_raises_when_confirming_below_min_size(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        confirm_update_data,
        user_id,
    ):
        """
        GIVEN DRAFT → CONFIRMED transition with members < min_team_size
        WHEN update_team is called
        THEN InvalidTeamSizeError raised
        """
        # Arrange
        mock_repository.get_team_members_count_or_raise.return_value = 1
        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(
            1, mock_contest.min_team_size, mock_contest.max_team_size
        )

        # Act & Assert
        with pytest.raises(InvalidTeamSizeError):
            await team_service.update_team(
                contest_id, team_id, confirm_update_data, user_id
            )

        mock_repository.update_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_team_size_called_with_correct_args(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        confirm_update_data,
        user_id,
    ):
        """
        GIVEN DRAFT → CONFIRMED transition
        WHEN update_team is called
        THEN validate_team_size called with member count, contest, status
        """
        # Arrange
        mock_repository.get_team_members_count_or_raise.return_value = 3
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, confirm_update_data, user_id
            )

        # Assert
        mock_validator.validate_team_size.assert_called_once_with(
            3, mock_contest, TeamStatus.CONFIRMED
        )


class TestUpdateTeamExecutionOrder:
    @pytest.mark.asyncio
    async def test_contest_fetched_before_guard(
        self,
        team_service,
        mock_repository,
        mock_guard,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN contest does not exist
        THEN guard never called
        """
        mock_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_guard.check_update_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_called_before_team_fetch(
        self,
        team_service,
        mock_guard,
        mock_repository,
        setup_valid_contest,  # ← contest passes, guard fails
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN guard raises PermissionDeniedError
        THEN get_contest_team_or_raise never called
        """
        mock_guard.check_update_team.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_repository.get_contest_team_or_raise.assert_not_called()

    @pytest.mark.asyncio
    async def test_team_fetched_before_name_validation(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest,  # ← contest passes, team fails
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN team not found
        THEN name validation never reached
        """
        mock_repository.get_contest_team_or_raise.side_effect = TeamNotFoundError(
            str(team_id), str(contest_id)
        )

        with pytest.raises(TeamNotFoundError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_validator.validate_name_unique.assert_not_called()

    @pytest.mark.asyncio
    async def test_name_validated_before_size_check(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        user_id,
    ):
        """
        GIVEN name validation fails
        THEN size check never reached
        """
        # Arrange — name change + CONFIRMED status together
        combined_update = TeamUpdate(
            name="Conflicting Name",
            description=None,
            logo=None,
            status=TeamStatus.CONFIRMED,
        )
        mock_repository.find_team_by_name.return_value = MagicMock()
        mock_validator.validate_name_unique.side_effect = TeamAlreadyExistsError(
            "Conflicting Name", str(contest_id)
        )

        with pytest.raises(TeamAlreadyExistsError):
            await team_service.update_team(
                contest_id, team_id, combined_update, user_id
            )

        mock_repository.get_team_members_count_or_raise.assert_not_called()


class TestUpdateTeamRepositoryContract:
    @pytest.mark.asyncio
    async def test_repository_called_with_correct_domain_object(
        self,
        team_service,
        mock_repository,
        mock_contest_team,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN all validations pass
        WHEN update_team is called
        THEN repository.update_team receives correctly mapped UpdateTeamData
        THIS IS THE CONTRACT — SQLAlchemy changes never break this
        """
        # Arrange
        mock_repository.find_team_by_name.return_value = None
        mock_repository.update_team.return_value = MagicMock()

        with patch.object(ContestTeamResponse, "from_contest_team"):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        # Assert exact domain object
        mock_repository.update_team.assert_called_once_with(
            UpdateTeamData(
                team_id=team_id,
                name=team_update_data.name,
                description=team_update_data.description,
                logo=team_update_data.logo,
                status=team_update_data.status,
            ),
            mock_contest_team.team,  # ← team extracted from contest_team
            mock_contest_team,  # ← contest_team itself
        )

    @pytest.mark.asyncio
    async def test_repository_never_called_when_name_validation_fails(
        self,
        team_service,
        mock_repository,
        mock_validator,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        team_update_data,
        user_id,
    ):
        """
        GIVEN name validation fails
        WHEN update_team is called
        THEN repository.update_team never called — no partial writes
        """
        # Arrange
        mock_repository.find_team_by_name.return_value = MagicMock()
        mock_validator.validate_name_unique.side_effect = TeamAlreadyExistsError(
            team_update_data.name, str(contest_id)
        )

        with pytest.raises(TeamAlreadyExistsError):
            await team_service.update_team(
                contest_id, team_id, team_update_data, user_id
            )

        mock_repository.update_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_repository_never_called_when_size_validation_fails(
        self,
        team_service,
        mock_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest_and_team,
        contest_id,
        team_id,
        confirm_update_data,
        user_id,
    ):
        """
        GIVEN size validation fails on CONFIRMED transition
        WHEN update_team is called
        THEN repository.update_team never called
        """
        # Arrange
        mock_repository.get_team_members_count_or_raise.return_value = 1
        mock_validator.validate_team_size.side_effect = InvalidTeamSizeError(
            1, mock_contest.min_team_size, mock_contest.max_team_size
        )

        with pytest.raises(InvalidTeamSizeError):
            await team_service.update_team(
                contest_id, team_id, confirm_update_data, user_id
            )

        mock_repository.update_team.assert_not_called()
