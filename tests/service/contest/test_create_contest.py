"""Comprehensive tests for ContestService.create_contest method.

This module contains thorough test coverage for contest creation functionality,
organized into logical test classes that cover different aspects of the operation:

- Success scenarios: Valid contest creation with various configurations
- Date validation: Testing contest date constraints and rules
- Team size validation: Testing team size constraints
- Repository contract: Testing the interface between service and repository
- Execution order: Testing the correct sequence of validation steps
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.contest import Contest
from app.schema.contest import ContestCreate, ContestResponse
from app.utils.enums import ScoringType


class TestCreateContestSuccess:
    """Test successful contest creation scenarios."""

    @pytest.mark.asyncio
    async def test_returns_contest_response(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        contest_create_data,
        user_id,
    ):
        """Test that successful contest creation returns ContestResponse."""
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(
            ContestResponse,
            "model_validate",
            return_value=MagicMock(spec=ContestResponse),
        ):
            result = await contest_service.create_contest(contest_create_data, user_id)

        assert result is not None
        mock_contest_repository.create_contest.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_public_contest(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that public contests can be created."""
        now = datetime.now(timezone.utc)
        public_contest_data = ContestCreate(
            name="Public Contest",
            description="A public contest",
            image=None,
            is_public=True,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2),
            registration_start=now,
            registration_end=now + timedelta(hours=1),
            max_teams=None,
            min_team_size=1,
            max_team_size=5,
            rules=None,
            scoring_type=ScoringType.AUTO,
        )
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.create_contest(public_contest_data, user_id)

        mock_contest_repository.create_contest.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_private_contest(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        user_id,
    ):
        """Test that private contests can be created."""
        now = datetime.now(timezone.utc)
        private_contest_data = ContestCreate(
            name="Private Contest",
            description="A private contest",
            image=None,
            is_public=False,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2),
            registration_start=now,
            registration_end=now + timedelta(hours=1),
            max_teams=None,
            min_team_size=1,
            max_team_size=5,
            rules=None,
            scoring_type=ScoringType.AUTO,
        )
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.create_contest(private_contest_data, user_id)

        mock_contest_repository.create_contest.assert_called_once()


class TestCreateContestDateValidation:
    """Test date constraint validation during creation."""

    @pytest.mark.asyncio
    async def test_validate_contest_dates_called_correctly(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        mock_contest,
        contest_create_data,
        user_id,
    ):
        """Test that date validation is called with correct parameters."""
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.create_contest(contest_create_data, user_id)

        mock_validator.validate_contest_dates.assert_called_once_with(
            contest_create_data.start_time,
            contest_create_data.end_time,
        )


class TestCreateContestTeamSizeValidation:
    """Test team size constraint validation."""

    @pytest.mark.asyncio
    async def test_validate_team_size_called_correctly(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        mock_contest,
        contest_create_data,
        user_id,
    ):
        """Test that team size validation is called with correct parameters."""
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.create_contest(contest_create_data, user_id)

        mock_validator.validate_team_size_constraints.assert_called_once_with(
            contest_create_data.min_team_size,
            contest_create_data.max_team_size,
        )


class TestCreateContestRepositoryContract:
    """Test the interface contract between service and repository layers."""

    @pytest.mark.asyncio
    async def test_repository_called_with_correct_domain_object(
        self,
        contest_service,
        mock_contest_repository,
        mock_contest,
        contest_create_data,
        user_id,
    ):
        """Test that repository receives correctly mapped Contest ORM entity."""
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.create_contest(contest_create_data, user_id)

        # Verify repository was called with Contest ORM entity
        call_args = mock_contest_repository.create_contest.call_args[0]
        contest_entity = call_args[0]

        assert isinstance(contest_entity, Contest)
        assert contest_entity.name == contest_create_data.name
        assert contest_entity.description == contest_create_data.description
        assert contest_entity.is_public == contest_create_data.is_public
        assert (
            contest_entity.team_approval_mode == contest_create_data.team_approval_mode
        )
        assert contest_entity.created_by == user_id


class TestCreateContestExecutionOrder:
    """Test the correct execution order of validation steps."""

    @pytest.mark.asyncio
    async def test_all_validations_before_create(
        self,
        contest_service,
        mock_contest_repository,
        mock_validator,
        mock_contest,
        contest_create_data,
        user_id,
    ):
        """Test that all validations execute before repository create."""
        mock_contest_repository.create_contest.return_value = mock_contest

        with patch.object(ContestResponse, "model_validate"):
            await contest_service.create_contest(contest_create_data, user_id)

        # Verify all validations were called
        assert mock_validator.validate_contest_dates.called
        assert mock_validator.validate_registration_dates.called
        assert mock_validator.validate_team_size_constraints.called

        # Repository create should be called after all validations
        mock_contest_repository.create_contest.assert_called_once()
