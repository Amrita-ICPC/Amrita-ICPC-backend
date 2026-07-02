from datetime import datetime, timezone
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.exceptions.bank import (
    BankAccessDeniedError,
    BankAlreadyExistsError,
    BankPermissionError,
)
from app.schema.bank import BankCreate, BankShareItem, BankUpdate
from app.utils.enums import BankPermission, BankSortBy

if TYPE_CHECKING:
    from app.service.bank_service import BankService


class MockBank:
    """A minimal mock representing a bank fetched from a database."""

    def __init__(self, **kwargs):
        self.shares = []
        self.questions = []
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_copy(self, update=None):
        new_obj = MockBank(**self.__dict__)
        if update:
            for k, v in update.items():
                setattr(new_obj, k, v)
        return new_obj


class MockBankShare:
    """A minimal mock representing a bank share configuration fetched from a database."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def mock_repository():
    """Provides a mocked BankRepository."""
    from app.repositories.bank import BankRepository

    return MagicMock(spec=BankRepository)


@pytest.fixture
def mock_validator():
    """Provides a mocked BankValidator."""
    from app.validators.bank import BankValidator

    return MagicMock(spec=BankValidator)


@pytest.fixture
def bank_service(mock_repository, mock_validator):
    """Provides a BankService instance equipped with mock dependencies."""
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
        from app.service.bank_service import BankService

        service = BankService(
            repository=mock_repository,
            validator=mock_validator,
        )
        yield service


@pytest.fixture
def sample_bank_data():
    """Returns baseline data for bank creation tasks."""
    return BankCreate(
        name="Test Bank",
        description="A test bank",
    )


@pytest.fixture
def existing_bank(sample_bank_data):
    """Returns a pre-populated MockBank simulating database existence."""
    bank_id = uuid4()
    creator_id = uuid4()
    return MockBank(
        id=bank_id,
        name=sample_bank_data.name,
        description=sample_bank_data.description,
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        total_questions_count=5,
    )


@pytest.mark.asyncio
async def test_create_bank_success(
    bank_service: "BankService",
    mock_repository,
    mock_validator,
    sample_bank_data,
    existing_bank,
):
    """Test successful creation of a bank."""
    user_id = existing_bank.created_by

    # Validator should not raise an exception
    mock_validator.validate_unique_bank_creation.return_value = None
    mock_repository.get_bank_by_name_and_creator.return_value = None
    mock_repository.create_bank.return_value = existing_bank

    result = await bank_service.create_bank(sample_bank_data, user_id)

    assert result.id == existing_bank.id
    assert result.name == existing_bank.name
    assert result.total_questions_count == 5
    mock_repository.add_share.assert_called_once_with(
        bank_id=existing_bank.id, user_id=user_id, permission=BankPermission.owner
    )


@pytest.mark.asyncio
async def test_create_bank_duplicate_name(
    bank_service: "BankService",
    mock_repository,
    mock_validator,
    sample_bank_data,
    existing_bank,
):
    """Test that creating a bank with duplicate name for same user raises error."""
    user_id = existing_bank.created_by

    mock_repository.get_bank_by_name_and_creator.return_value = existing_bank
    mock_validator.validate_unique_bank_creation.side_effect = BankAlreadyExistsError(
        sample_bank_data.name
    )

    with pytest.raises(BankAlreadyExistsError):
        await bank_service.create_bank(sample_bank_data, user_id)


@pytest.mark.asyncio
async def test_update_bank_owner_success(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test owner can update bank."""
    update_data = BankUpdate(name="Updated Bank Name")
    mock_repository.get_bank_or_raise.return_value = existing_bank

    # Mock validation and update
    mock_validator.construct_valid_update_payload.return_value = {
        "name": "Updated Bank Name"
    }

    updated_bank = MockBank(**existing_bank.__dict__)
    updated_bank.name = "Updated Bank Name"
    mock_repository.update_bank.return_value = updated_bank

    await bank_service.update_bank(
        existing_bank.id, update_data, existing_bank.created_by
    )

    mock_validator.check_edit_bank.assert_called_once()
    mock_validator.construct_valid_update_payload.assert_called_once()
    mock_repository.update_bank.assert_called_once()


@pytest.mark.asyncio
async def test_update_bank_permission_denied(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test non-owner/non-editor cannot update bank."""
    update_data = BankUpdate(name="New Name")
    random_user_id = uuid4()

    mock_repository.get_bank_or_raise.return_value = existing_bank
    mock_validator.check_edit_bank.side_effect = BankAccessDeniedError()

    with pytest.raises(BankAccessDeniedError):
        await bank_service.update_bank(existing_bank.id, update_data, random_user_id)


@pytest.mark.asyncio
async def test_delete_bank_owner_success(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test owner can delete bank."""
    mock_repository.get_bank_or_raise.return_value = existing_bank

    await bank_service.delete_bank(existing_bank.id, existing_bank.created_by)

    mock_validator.check_manage_bank.assert_called_once()
    mock_repository.delete_bank.assert_called_once_with(existing_bank)


@pytest.mark.asyncio
async def test_delete_bank_denied(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test non-owner cannot delete bank."""
    random_user_id = uuid4()
    mock_repository.get_bank_or_raise.return_value = existing_bank
    mock_validator.check_manage_bank.side_effect = BankPermissionError()

    with pytest.raises(BankPermissionError):
        await bank_service.delete_bank(existing_bank.id, random_user_id)


@pytest.mark.asyncio
async def test_share_bank_denied(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test non-owner cannot share bank."""
    shares = [BankShareItem(user_id=uuid4(), permission=BankPermission.read)]
    random_user_id = uuid4()

    mock_repository.get_bank_or_raise.return_value = existing_bank
    mock_validator.check_manage_bank.side_effect = BankPermissionError()

    with pytest.raises(BankPermissionError):
        await bank_service.share_bank(existing_bank.id, shares, random_user_id)


@pytest.mark.asyncio
async def test_get_soft_deleted_banks_success(
    bank_service, mock_repository, existing_bank
):
    """Test owner can fetch softly deleted banks."""
    user_id = existing_bank.created_by

    from app.repositories.dto import PaginatedResult

    deleted_bank = MockBank(**existing_bank.__dict__)
    deleted_bank.is_deleted = True

    mock_paginated = PaginatedResult(total=1, items=[deleted_bank])
    mock_repository.get_soft_deleted_banks.return_value = mock_paginated

    total, items = await bank_service.get_soft_deleted_banks(
        user_id=user_id, skip=0, limit=10
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].id == existing_bank.id
    assert items[0].total_questions_count == 5
    mock_repository.get_soft_deleted_banks.assert_called_once()


@pytest.mark.asyncio
async def test_soft_delete_bank_owner_success(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test owner can soft delete a bank."""
    mock_repository.get_bank_or_raise.return_value = existing_bank

    await bank_service.soft_delete_bank(existing_bank.id, existing_bank.created_by)

    mock_validator.check_manage_bank.assert_called_once()
    mock_repository.soft_delete_bank.assert_called_once_with(
        existing_bank, existing_bank.created_by
    )


@pytest.mark.asyncio
async def test_restore_bank_owner_success(
    bank_service, mock_repository, mock_validator, existing_bank
):
    """Test owner can restore a softly deleted bank."""
    deleted_bank = MockBank(**existing_bank.__dict__)
    deleted_bank.is_deleted = True

    restored_bank = MockBank(**existing_bank.__dict__)
    restored_bank.is_deleted = False

    mock_repository.get_deleted_bank_or_raise.return_value = deleted_bank
    mock_repository.restore_bank.return_value = restored_bank

    result = await bank_service.restore_bank(existing_bank.id, existing_bank.created_by)

    mock_validator.check_manage_bank.assert_called_once()
    mock_repository.get_deleted_bank_or_raise.assert_called_once_with(existing_bank.id)
    mock_repository.restore_bank.assert_called_once_with(deleted_bank)
    assert result.id == existing_bank.id


@pytest.mark.asyncio
async def test_get_all_banks_with_search_and_sort(
    bank_service, mock_repository, existing_bank
):
    """Test get_all_banks with sorting and searching parameters."""
    user_id = existing_bank.created_by
    from app.repositories.dto import PaginatedResult

    mock_paginated = PaginatedResult(total=1, items=[existing_bank])
    mock_repository.get_banks_with_filters.return_value = mock_paginated

    total, items = await bank_service.get_all_banks(
        user_id=user_id,
        skip=0,
        limit=10,
        search_term="Test",
        sort_by=BankSortBy.NAME,
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].id == existing_bank.id
    assert items[0].total_questions_count == 5

    # Verify the parameters passed to get_banks_with_filters
    mock_repository.get_banks_with_filters.assert_called_once()
    args, kwargs = mock_repository.get_banks_with_filters.call_args
    assert kwargs["user_id"] == user_id
    assert kwargs["filters"].search_term == "Test"
    assert kwargs["filters"].sort_by == BankSortBy.NAME
    assert kwargs["pagination"].skip == 0
    assert kwargs["pagination"].limit == 10
