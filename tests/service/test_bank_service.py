from datetime import datetime, timezone
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.exceptions.auth import PermissionDeniedError
from app.exceptions.bank import (
    BankAccessDeniedError,
    BankAlreadyExistsError,
    BankNotFoundError,
    BankPermissionError,
)
from app.models.bank import Bank, BankShare
from app.schema.bank import BankCreate, BankUpdate, BankShareItem, BankShareRequest
from app.utils.enums import BankPermission

if TYPE_CHECKING:
    from app.service.bank_service import BankService


class MockBank:
    def __init__(self, **kwargs):
        self.shares = []
        self.questions = []
        for key, value in kwargs.items():
            setattr(self, key, value)
            
    def model_copy(self, update=None):
        # Simple mock for model_copy used in get_bank_by_id for Pydantic models
        # In the service, the return value from _get_bank_from_cache is a Pydantic model
        # But here we might be mocking the return of _get_bank_from_cache
        new_obj = MockBank(**self.__dict__)
        if update:
            for k, v in update.items():
                setattr(new_obj, k, v)
        return new_obj


class MockBankShare:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def bank_service(mock_db):
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
        from app.service.bank_service import BankService

        service = BankService(mock_db)
        yield service


@pytest.fixture
def sample_bank_data():
    return BankCreate(
        name="Test Bank",
        description="A test bank",
    )


@pytest.fixture
def existing_bank(sample_bank_data):
    bank_id = uuid4()
    creator_id = uuid4()
    return MockBank(
        id=bank_id,
        name=sample_bank_data.name,
        description=sample_bank_data.description,
        created_by=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_create_bank_success(
    bank_service: "BankService", mock_db, sample_bank_data, existing_bank
):
    """Test successful creation of a bank."""
    user_id = existing_bank.created_by

    # Mock query to return None (no duplicate)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Mock refresh to update the instance with ID
    def side_effect_refresh(instance):
        instance.id = existing_bank.id
        instance.created_at = existing_bank.created_at
        instance.updated_at = existing_bank.updated_at
        return None

    mock_db.refresh.side_effect = side_effect_refresh

    result = await bank_service.create_bank(sample_bank_data, user_id)

    assert result.id == existing_bank.id
    assert result.name == existing_bank.name
    # Called twice: once for Bank, once for BankShare (Owner)
    assert mock_db.add.call_count == 2
    # Flush called twice too
    assert mock_db.flush.call_count == 2
    mock_db.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_create_bank_duplicate_name(
    bank_service: "BankService", mock_db, sample_bank_data, existing_bank
):
    """Test that creating a bank with duplicate name for same user raises error."""
    user_id = existing_bank.created_by

    # Mock query to return existing bank
    mock_db.query.return_value.filter.return_value.first.return_value = existing_bank

    with pytest.raises(BankAlreadyExistsError):
        await bank_service.create_bank(sample_bank_data, user_id)


@pytest.mark.asyncio
async def test_get_bank_by_id_owner(bank_service, mock_db, existing_bank):
    """Test owner can retrieve bank and sees shares (even if empty)."""
    
    from app.schema.bank import BankDetailResponse
    
    bank_response = BankDetailResponse(
        id=existing_bank.id,
        name=existing_bank.name,
        description=existing_bank.description,
        created_by=existing_bank.created_by,
        created_at=existing_bank.created_at,
        updated_at=existing_bank.updated_at,
        questions=[],
        shares=[]
    )
    
    with patch.object(bank_service, '_get_bank_from_cache', return_value=bank_response):
        result = await bank_service.get_bank_by_id(existing_bank.id, existing_bank.created_by)
        
        assert result.id == existing_bank.id
        assert result.shares == []


@pytest.mark.asyncio
async def test_get_bank_by_id_shared_read(bank_service, mock_db, existing_bank):
    """Test shared user can retrieve bank but shares list is hidden."""
    shared_user_id = uuid4()
    
    from app.schema.bank import BankDetailResponse, BankShareBase
    
    share_info = BankShareBase(user_id=shared_user_id, permission=BankPermission.read)
    
    bank_response = BankDetailResponse(
        id=existing_bank.id,
        name=existing_bank.name,
        description=existing_bank.description,
        created_by=existing_bank.created_by,
        created_at=existing_bank.created_at,
        updated_at=existing_bank.updated_at,
        questions=[],
        shares=[share_info]
    )
    
    with patch.object(bank_service, '_get_bank_from_cache', return_value=bank_response):
        result = await bank_service.get_bank_by_id(existing_bank.id, shared_user_id)
        
        assert result.id == existing_bank.id
        assert result.shares == []


@pytest.mark.asyncio
async def test_get_bank_by_id_access_denied(bank_service, mock_db, existing_bank):
    """Test unauthorized user cannot retrieve bank."""
    random_user_id = uuid4()
    
    from app.schema.bank import BankDetailResponse
    
    bank_response = BankDetailResponse(
        id=existing_bank.id,
        name=existing_bank.name,
        description=existing_bank.description,
        created_by=existing_bank.created_by,
        created_at=existing_bank.created_at,
        updated_at=existing_bank.updated_at,
        questions=[],
        shares=[]
    )
    
    with patch.object(bank_service, '_get_bank_from_cache', return_value=bank_response):
        with pytest.raises(BankAccessDeniedError):
            await bank_service.get_bank_by_id(existing_bank.id, random_user_id)


@pytest.mark.asyncio
async def test_update_bank_owner_success(bank_service, mock_db, existing_bank):
    """Test owner can update bank."""
    update_data = BankUpdate(name="Updated Bank Name")
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Bank:
            mock.filter.return_value.first.return_value = existing_bank
        return mock
        
    mock_db.query.side_effect = query_side_effect
    
    result = await bank_service.update_bank(existing_bank.id, update_data, existing_bank.created_by)
    
    assert existing_bank.name == "Updated Bank Name"
    mock_db.flush.assert_called_once()
    mock_db.refresh.assert_called_with(existing_bank)


@pytest.mark.asyncio
async def test_update_bank_permission_denied(bank_service, mock_db, existing_bank):
    """Test non-owner/non-editor cannot update bank."""
    update_data = BankUpdate(name="New Name")
    random_user_id = uuid4()
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Bank:
            mock.filter.return_value.first.return_value = existing_bank
        elif model == BankShare:
            mock.filter.return_value.first.return_value = None
        return mock

    mock_db.query.side_effect = query_side_effect
    
    with pytest.raises(BankAccessDeniedError):
        await bank_service.update_bank(existing_bank.id, update_data, random_user_id)


@pytest.mark.asyncio
async def test_delete_bank_owner_success(bank_service, mock_db, existing_bank):
    """Test owner can delete bank."""
    mock_db.query.return_value.filter.return_value.first.return_value = existing_bank
    
    await bank_service.delete_bank(existing_bank.id, existing_bank.created_by)
    
    mock_db.delete.assert_called_once_with(existing_bank)
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_delete_bank_denied(bank_service, mock_db, existing_bank):
    """Test non-owner cannot delete bank."""
    random_user_id = uuid4()
    mock_db.query.return_value.filter.return_value.first.return_value = existing_bank
    
    with pytest.raises(BankPermissionError):
        await bank_service.delete_bank(existing_bank.id, random_user_id)


@pytest.mark.asyncio
async def test_share_bank_owner_success(bank_service, mock_db, existing_bank):
    """Test owner can share bank."""
    target_user_id = uuid4()
    shares = [BankShareItem(user_id=target_user_id, permission=BankPermission.read)]
    
    def query_side_effect(model):
        mock = MagicMock()
        if model == Bank:
            mock.filter.return_value.first.return_value = existing_bank
        elif model == BankShare:
            mock.filter.return_value.first.return_value = None
        return mock

    mock_db.query.side_effect = query_side_effect
    
    await bank_service.share_bank(existing_bank.id, shares, existing_bank.created_by)
    
    mock_db.add.assert_called_once() 
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_share_bank_denied(bank_service, mock_db, existing_bank):
    """Test non-owner cannot share bank."""
    shares = [BankShareItem(user_id=uuid4(), permission=BankPermission.read)]
    random_user_id = uuid4()
    
    mock_db.query.return_value.filter.return_value.first.return_value = existing_bank
    
    with pytest.raises(BankPermissionError):
        await bank_service.share_bank(existing_bank.id, shares, random_user_id)


@pytest.mark.asyncio
async def test_unshare_bank_owner_success(bank_service, mock_db, existing_bank):
    """Test owner can unshare bank."""
    target_user_id = uuid4()
    user_ids = [target_user_id]
    
    mock_share = MockBankShare(bank_id=existing_bank.id, user_id=target_user_id)

    def query_side_effect(model):
        mock = MagicMock()
        if model == Bank:
            mock.filter.return_value.first.return_value = existing_bank
        elif model == BankShare:
            mock.filter.return_value.first.return_value = mock_share
        return mock

    mock_db.query.side_effect = query_side_effect
    
    await bank_service.unshare_bank(existing_bank.id, user_ids, existing_bank.created_by)
    
    mock_db.delete.assert_called_once_with(mock_share)
    mock_db.flush.assert_called_once()
