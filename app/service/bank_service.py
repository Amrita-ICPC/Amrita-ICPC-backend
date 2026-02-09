from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.exceptions.bank import (
    BankAccessDeniedError,
    BankAlreadyExistsError,
    BankNotFoundError,
    BankPermissionError,
)
from app.models.bank import Bank, BankShare
from app.schema.bank import BankCreate, BankUpdate, BankShareItem, BankResponse, BankDetailResponse
from app.utils.enums import BankPermission


class BankService:
    """Service for bank database operations."""

    def __init__(self, db: Session):
        self.db = db

    @cache_delete(
        key_builder=lambda self, bank, user_id: f"banks:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda result: f"bank:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def create_bank(
        self, bank: BankCreate, user_id: UUID
    ) -> BankResponse:
        """Create a new bank."""
        existing_bank = self.db.query(Bank).filter(
            Bank.name == bank.name,
            Bank.created_by == user_id
        ).first()
        if existing_bank:
            raise BankAlreadyExistsError(bank.name)
            
        db_bank = Bank(
            name=bank.name,
            description=bank.description,
            created_by=user_id
        )
        self.db.add(db_bank)
        self.db.flush()
        self.db.refresh(db_bank)
        
        # Grant OWNER access to creator
        share = BankShare(
            bank_id=db_bank.id,
            user_id=user_id,
            permission=BankPermission.owner
        )
        self.db.add(share)
        self.db.flush()

        return BankResponse.model_validate(db_bank)

    @cache_get(
        key_builder=lambda self, bank_id: f"bank:{bank_id}",
        ttl=300,
    )
    async def _get_bank_from_cache(self, bank_id: UUID) -> BankDetailResponse:
        """
        Internal method to get bank from DB with caching.
        WARNING: Does not check permissions!
        """
        stmt = (
            self.db.query(Bank)
            .options(joinedload(Bank.questions), joinedload(Bank.shares))
            .filter(Bank.id == bank_id)
        )
        bank = stmt.first()
        
        if not bank:
            raise BankNotFoundError(str(bank_id))
            
        return BankDetailResponse.model_validate(bank)

    async def get_bank_by_id(
        self, bank_id: UUID, user_id: UUID, check_access: bool = True
    ) -> BankDetailResponse:
        """
        Get bank by ID with permission checks and visibility filtering.
        """
        # Get bank from cache (or DB)
        bank = await self._get_bank_from_cache(bank_id)
            
        if check_access:
            # Check ownership or share
            if bank.created_by == user_id:
                # Owner sees everything
                pass 
            else:
                # Check share
                # We can check the shares list in the cached object since it includes all shares
                # This avoids hitting the DB again
                has_access = False
                for share in bank.shares:
                    if share.user_id == user_id:
                        has_access = True
                        break
                
                if not has_access:
                    raise BankAccessDeniedError()
                
                # Non-owners should not see the shares list
                # We create a copy or modify the Pydantic model response
                # Since Pydantic models are immutable by default in v2 but we are using v1 style or Config, 
                # we can use model_copy with update, or just set the field if it's a standard model
                # app.schema.bank.BankDetailResponse seems to be a standard BaseModel
                
                # Create a copy with empty shares
                bank = bank.model_copy(update={"shares": []})

        return bank

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=100: f"banks:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_all_banks(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[BankResponse]]:
        """Get all banks accessible to the user (Owned + Shared)."""
        query = self.db.query(Bank).outerjoin(BankShare).filter(
            or_(
                Bank.created_by == user_id,
                BankShare.user_id == user_id
            )
        ).distinct()
        
        total = query.count()
        banks = query.offset(skip).limit(limit).all()
        return total, [BankResponse.model_validate(bank) for bank in banks]

    @cache_delete(
        key_builder=lambda self, bank_id, bank_update, user_id: f"banks:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda result: f"bank:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def update_bank(
        self, bank_id: UUID, bank_update: BankUpdate, user_id: UUID
    ) -> BankResponse:
        """Update a bank."""
        # We need the raw DB object here to check permissions and update,
        # but get_bank_by_id returns Pydantic model due to cache decorator.
        # So we query directly or use a private helper.
        # Private helper avoid circular cache logic issues.
        
        bank = self.db.query(Bank).filter(Bank.id == bank_id).first()
        if not bank:
            raise BankNotFoundError(str(bank_id))
        
        # Check permissions for edit
        if bank.created_by != user_id:
            share = self.db.query(BankShare).filter(
                BankShare.bank_id == bank_id,
                BankShare.user_id == user_id
            ).first()
            
            if share and share.permission == BankPermission.read:
                raise BankPermissionError()
            
            if not share:
                 raise BankAccessDeniedError()

        update_data = bank_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "name" and (value is None or value.strip() == ""):
                continue
            setattr(bank, field, value)

        self.db.flush()
        self.db.refresh(bank)
        return BankResponse.model_validate(bank)

    @cache_delete(
        key_builder=lambda self, bank_id, user_id: [
            f"bank:{bank_id}",
            f"banks:user:{user_id}:*",
        ]
    )
    async def delete_bank(self, bank_id: UUID, user_id: UUID) -> None:
        """Delete a bank."""
        bank = self.db.query(Bank).filter(Bank.id == bank_id).first()
        if not bank:
             raise BankNotFoundError(str(bank_id))
        
        # Only Owner can delete
        if bank.created_by != user_id:
             raise BankPermissionError()

        self.db.delete(bank)
        self.db.flush()

    @cache_delete(
        key_builder=lambda self, bank_id, shares, current_user_id: [
            f"bank:{bank_id}", # Invalidate bank details as shares change
            # We might want to invalidate target users' lists too but that requires knowning target user IDs.
            # shares is a list of objects.
        ]
    )
    async def share_bank(
        self, bank_id: UUID, shares: List[BankShareItem], current_user_id: UUID
    ) -> None:
        """Share a bank with multiple users or transfer ownership."""
        bank = self.db.query(Bank).filter(Bank.id == bank_id).first()
        if not bank:
            raise BankNotFoundError(str(bank_id))
        
        # Access Check: Only Owner can share
        is_owner = (bank.created_by == current_user_id)
        if not is_owner:
             raise BankPermissionError()

        for share_item in shares:
            target_user_id = share_item.user_id
            permission = share_item.permission

            # Handle Ownership Transfer
            if permission == BankPermission.owner:
                # Transfer ownership
                # 1. Update Bank
                bank.created_by = target_user_id
                
                # 2. Update Old Owner (Current User) -> EDIT
                old_owner_share = self.db.query(BankShare).filter(
                    BankShare.bank_id == bank_id,
                    BankShare.user_id == current_user_id
                ).first()
                
                if old_owner_share:
                    old_owner_share.permission = BankPermission.edit
                else:
                    self.db.add(BankShare(
                        bank_id=bank_id, 
                        user_id=current_user_id, 
                        permission=BankPermission.edit
                    ))
                
                # 3. Update New Owner -> OWNER
                # Check if target user already had a share
                new_owner_share = self.db.query(BankShare).filter(
                    BankShare.bank_id == bank_id,
                    BankShare.user_id == target_user_id
                ).first()
                
                if new_owner_share:
                    new_owner_share.permission = BankPermission.owner
                else:
                    self.db.add(BankShare(
                        bank_id=bank_id, 
                        user_id=target_user_id, 
                        permission=BankPermission.owner
                    ))
                    
            else:
                # Normal Sharing (Read/Edit)
                existing_share = self.db.query(BankShare).filter(
                    BankShare.bank_id == bank_id,
                    BankShare.user_id == target_user_id
                ).first()

                if existing_share:
                    existing_share.permission = permission
                else:
                    new_share = BankShare(
                        bank_id=bank_id,
                        user_id=target_user_id,
                        permission=permission
                    )
                    self.db.add(new_share)
        
        self.db.flush()


    @cache_delete(
         key_builder=lambda self, bank_id, user_ids, current_user_id: [
            f"bank:{bank_id}",
         ]
    )
    async def unshare_bank(
        self, bank_id: UUID, user_ids: List[UUID], current_user_id: UUID
    ) -> None:
        """Remove users from bank shares."""
        bank = self.db.query(Bank).filter(Bank.id == bank_id).first()
        if not bank:
             raise BankNotFoundError(str(bank_id))
        
        # Access Check: Only Owner can unshare
        is_owner = (bank.created_by == current_user_id)
        if not is_owner:
             raise BankPermissionError()

        for target_user_id in user_ids:
            # Cannot remove owner via unshare (must transfer ownership via share endpoint)
            if target_user_id == bank.created_by:
                continue

            share = self.db.query(BankShare).filter(
                BankShare.bank_id == bank_id,
                BankShare.user_id == target_user_id
            ).first()
            
            if share:
                self.db.delete(share)
        
        self.db.flush()
