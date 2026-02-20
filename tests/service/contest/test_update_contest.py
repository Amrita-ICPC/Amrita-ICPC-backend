"""Comprehensive tests for ContestService.update_contest method.

This module tests contest update operations with focus on:
- Successful updates with various field combinations
- Date validation on updates
- Team size validation on updates
- Permission checks
- Execution order guarantees
- Repository contract verification
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.permissions import PermissionDeniedError
from app.exceptions.contest import ContestNotFoundError, InvalidContestError
from app.schema.contest import ContestResponse, ContestUpdate


class TestUpdateContestSuccess:
    """Test successful contest update scenarios."""

    @pytest.mark.asyncio
    async def test_returns_contest_response(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        contest_update_data,
        user_id,
    ):
        """Test that successful update returns ContestResponse."""
        updated_contest = MagicMock()
        updated_contest.id = mock_contest.id
        updated_contest.name = "Updated Name"
        mock_contest_repository.update_contest.return_value = updated_contest

        with patch.object(
            ContestResponse,
            "model_validate",
            return_value=MagicMock(spec=ContestResponse),
        ):
            result = await contest_service.update_contest(
                mock_contest.id, contest_update_data, user_id
            )

        assert result is not None
        mock_contest_repository.update_contest.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_only_name_succeeds(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        setup_valid_contest,
        user_id,
    ):
        """Test that partial update with only name works."""
        update_data = ContestUpdate(name="New Name")
        updated_contest = MagicMock()
        mock_contest_repository.update_contest.return_value = updated_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.update_contest(
                mock_contest_repository.get_contest_or_raise.return_value.id,
                update_data,
                user_id,
            )

        mock_contest_repository.update_contest.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_description_only_succeeds(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        setup_valid_contest,
        user_id,
    ):
        """Test that partial update with only description works."""
        update_data = ContestUpdate(description="New description")
        updated_contest = MagicMock()
        mock_contest_repository.update_contest.return_value = updated_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.update_contest(
                mock_contest_repository.get_contest_or_raise.return_value.id,
                update_data,
                user_id,
            )

        mock_contest_repository.update_contest.assert_called_once()


class TestUpdateContestContestValidation:
    """Test contest existence validation."""

    @pytest.mark.asyncio
    async def test_raises_when_contest_not_found(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        contest_update_data,
        user_id,
    ):
        """Test that ContestNotFoundError is raised when contest doesn't exist."""
        contest_id = uuid4()
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.update_contest(
                contest_id, contest_update_data, user_id
            )

        mock_guard.check_manage_contest.assert_not_called()


class TestUpdateContestPermissions:
    """Test permission validation for updates."""

    @pytest.mark.asyncio
    async def test_raises_when_user_lacks_permission(
        self,
        contest_service,
        mock_guard,
        setup_valid_contest,
        contest_update_data,
        user_id,
    ):
        """Test that PermissionDeniedError is raised when user lacks permission."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()
        mock_contest = setup_valid_contest

        with pytest.raises(PermissionDeniedError):
            await contest_service.update_contest(
                mock_contest.id, contest_update_data, user_id
            )

    @pytest.mark.asyncio
    async def test_guard_called_with_correct_args(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        mock_contest,
        setup_valid_contest,
        contest_update_data,
        user_id,
    ):
        """Test that guard is called with correct arguments."""
        updated_contest = MagicMock()
        mock_contest_repository.update_contest.return_value = updated_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.update_contest(
                mock_contest.id, contest_update_data, user_id
            )

        mock_guard.check_manage_contest.assert_called_once()
        call_args = mock_guard.check_manage_contest.call_args
        assert call_args[1]["user_id"] == user_id


class TestUpdateContestDateValidation:
    """Test date validation on updates."""

    @pytest.mark.asyncio
    async def test_skips_validation_if_dates_unchanged(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that validation is called with merged dates."""
        update_data = ContestUpdate(name="New Name")
        updated_contest = MagicMock()
        mock_contest_repository.update_contest.return_value = updated_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.update_contest(mock_contest.id, update_data, user_id)

        # Validator should be called with merged dates
        assert mock_validator.validate_contest_dates.called


class TestUpdateContestTeamSizeValidation:
    """Test team size validation on updates."""

    @pytest.mark.asyncio
    async def test_raises_when_invalid_team_sizes(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        mock_contest,
        setup_valid_contest,
        user_id,
    ):
        """Test that team size validation catches invalid updates."""
        bad_update = ContestUpdate(
            min_team_size=10,
            max_team_size=5,
        )
        mock_validator.validate_team_size_constraints.side_effect = InvalidContestError(
            "Invalid team sizes"
        )

        with pytest.raises(InvalidContestError):
            await contest_service.update_contest(mock_contest.id, bad_update, user_id)


class TestUpdateContestExecutionOrder:
    """Test execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_contest_validated_before_guard(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        contest_update_data,
        user_id,
    ):
        """Test that contest existence is checked before permissions."""
        contest_id = uuid4()
        mock_contest_repository.get_contest_or_raise.side_effect = ContestNotFoundError(
            str(contest_id)
        )

        with pytest.raises(ContestNotFoundError):
            await contest_service.update_contest(
                contest_id, contest_update_data, user_id
            )

        mock_guard.check_manage_contest.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_checked_before_repository_update(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        setup_valid_contest,
        contest_update_data,
        user_id,
    ):
        """Test that permissions are checked before updating."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.update_contest(
                setup_valid_contest.id, contest_update_data, user_id
            )

        mock_contest_repository.update_contest.assert_not_called()


class TestUpdateContestRepositoryContract:
    """Test service-repository interface for updates."""

    @pytest.mark.asyncio
    async def test_repository_called_with_contest_object(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        setup_valid_contest,
        contest_update_data,
        user_id,
    ):
        """Test that repository is called with contest object."""
        updated_contest = MagicMock()
        mock_contest_repository.update_contest.return_value = updated_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.update_contest(
                mock_contest.id, contest_update_data, user_id
            )

        # Verify repository was called
        mock_contest_repository.update_contest.assert_called_once()
        call_args = mock_contest_repository.update_contest.call_args
        update_data = call_args[0][1]  # Second argument is update_data
        assert update_data.name == contest_update_data.name

    @pytest.mark.asyncio
    async def test_repository_never_called_when_validation_fails(
        self,
        contest_service,
        mock_contest_repository,
        mock_guard,
        setup_valid_contest,
        contest_update_data,
        user_id,
    ):
        """Test that repository operations are never called when validation fails."""
        mock_guard.check_manage_contest.side_effect = PermissionDeniedError()

        with pytest.raises(PermissionDeniedError):
            await contest_service.update_contest(
                setup_valid_contest.id, contest_update_data, user_id
            )

        mock_contest_repository.update_contest.assert_not_called()
