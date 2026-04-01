from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.repositories.bank import BankRepository
from app.repositories.dto.bank import BankFilters
from app.repositories.dto.pagination import PaginationParams
from app.schema.bank import (
    BankCreate,
    BankDetailResponse,
    BankResponse,
    BankShareItem,
    BankUpdate,
)
from app.utils.enums import BankPermission
from app.validators.bank import BankValidator


class BankService:
    """Service layer coordinating bank logic through injected repositories and guards.

    This service orchestrates bank-related business logic by coordinating
    between the repository layer (data access), guard layer (permissions),
    and validator layer (business rules). This implements a clean architecture
    pattern separating concerns completely from database or API knowledge.
    """

    def __init__(
        self,
        repository: BankRepository,
        validator: BankValidator,
    ):
        """Initialize the bank service layer dependencies.

        Args:
            repository (BankRepository): Data access gateway.
            validator (BankValidator): Schema and logic validation.
        """
        self.repository = repository
        self.validator = validator

    @cache_delete(
        key_builder=lambda self, bank, user_id: f"banks:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda result: f"bank:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def create_bank(self, bank: BankCreate, user_id: UUID) -> BankResponse:
        """Create a new bank under the current user's ownership.

        Args:
            bank (BankCreate): Bank specification details.
            user_id (UUID): The creating user.

        Returns:
            BankResponse: Exposes public attributes of the newly created bank.

        Raises:
            BankAlreadyExistsError: If this user already created a bank with this exact name.
        """
        existing = await self.repository.get_bank_by_name_and_creator(
            name=bank.name, user_id=user_id
        )
        self.validator.validate_unique_bank_creation(existing, bank.name)

        db_bank = await self.repository.create_bank(bank_data=bank, user_id=user_id)

        # Grant ownership instantly via share relationships
        await self.repository.add_share(
            bank_id=db_bank.id, user_id=user_id, permission=BankPermission.owner
        )

        return BankResponse.model_validate(db_bank)

    @cache_get(
        key_builder=lambda self, bank_id: f"bank:{bank_id}",
        ttl=300,
    )
    async def _get_bank_from_cache(self, bank_id: UUID) -> BankDetailResponse:
        """Internal helper handling explicit cache access for bank structure.

        WARNING: This skips access checks intentionally to load entities uniformly.

        Args:
            bank_id (UUID): Fetching by database ID.

        Returns:
            BankDetailResponse: Serialized data representation from DB.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        return BankDetailResponse.model_validate(bank)

    async def get_bank_by_id(
        self, bank_id: UUID, user_id: UUID, check_access: bool = True
    ) -> BankDetailResponse:
        """Fetch bank specific details including relationships, heavily guarded.

        Args:
            bank_id (UUID): Focus entity ID.
            user_id (UUID): Requesting agent ID.
            check_access (bool): Whether to enforce READ constraints.

        Returns:
            BankDetailResponse: A complete detail breakdown of structure.
        """
        cached_dto = await self._get_bank_from_cache(bank_id)

        if check_access:
            # We recreate a mock 'bank' locally from DTO since guard expects model interfaces
            # Alternatively we could decouple guard to use arbitrary dicts or pass the DTO
            # Converting to standard validation checks
            class MinimalBankMock:
                created_by = cached_dto.created_by
                shares = cached_dto.shares

            self.validator.check_read_bank(user_id=user_id, bank=MinimalBankMock())  # type: ignore

            if cached_dto.created_by != user_id:
                # Strip out comprehensive admin detail lists for regular readers
                cached_dto = cached_dto.model_copy(update={"shares": []})

        return cached_dto

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
        """Fetch a paginated block of available banks scoped to the caller.

        Args:
            user_id (UUID): Target entity fetching list.
            skip (int): Records to advance before streaming.
            limit (int): Max records back-streamed.

        Returns:
            tuple[int, List[BankResponse]]: Total row size available globally vs fetched subset.
        """
        filters = BankFilters()
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.repository.get_banks_with_filters(
            user_id=user_id, filters=filters, pagination=pagination
        )

        responses = [BankResponse.model_validate(b) for b in result.items]
        return result.total, responses

    @cache_delete(
        key_builder=lambda self,
        bank_id,
        bank_update,
        user_id: f"banks:user:{user_id}:*",
    )
    @cache_set(
        key_builder=lambda result: f"bank:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def update_bank(
        self, bank_id: UUID, bank_update: BankUpdate, user_id: UUID
    ) -> BankResponse:
        """Partially update internal specifications regarding a bank entity.

        Args:
            bank_id (UUID): Selection block targeting specific bank.
            bank_update (BankUpdate): Safe schema input wrapping possible modifications.
            user_id (UUID): Identity handling the patch.

        Returns:
            BankResponse: Serialized modified entity mapping to DB.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_edit_bank(user_id=user_id, bank=bank)

        update_data = bank_update.model_dump(exclude_unset=True)
        validated_data = self.validator.construct_valid_update_payload(update_data)

        for field, value in validated_data.items():
            setattr(bank, field, value)

        updated_bank = await self.repository.update_bank(bank)
        return BankResponse.model_validate(updated_bank)

    @cache_delete(
        key_builder=lambda self, bank_id, user_id: [
            f"bank:{bank_id}",
            f"banks:user:{user_id}:*",
        ]
    )
    async def delete_bank(self, bank_id: UUID, user_id: UUID) -> None:
        """Force erase an entire bank node including associative metadata.

        Args:
            bank_id (UUID): Pointer to exact resource.
            user_id (UUID): Deletion agent forcing execution.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_manage_bank(user_id=user_id, bank=bank)
        await self.repository.delete_bank(bank)

    @cache_get(
        key_builder=lambda self,
        user_id,
        skip=0,
        limit=100: f"banks:deleted:user:{user_id}:skip:{skip}:limit:{limit}",
        ttl=300,
    )
    async def get_soft_deleted_banks(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[int, List[BankResponse]]:
        """Fetch a paginated block of softly deleted banks scoped to the caller.

        Args:
            user_id (UUID): Target entity fetching list.
            skip (int): Records to advance before streaming.
            limit (int): Max records back-streamed.

        Returns:
            tuple[int, List[BankResponse]]: Total row size available vs fetched subset.
        """
        filters = BankFilters()
        pagination = PaginationParams(skip=skip, limit=limit)

        result = await self.repository.get_soft_deleted_banks(
            user_id=user_id, filters=filters, pagination=pagination
        )

        responses = [BankResponse.model_validate(b) for b in result.items]
        return result.total, responses

    @cache_delete(
        key_builder=lambda self, bank_id, user_id: [
            f"bank:{bank_id}",
            f"banks:user:{user_id}:*",
            f"banks:deleted:user:{user_id}:*",
        ]
    )
    async def soft_delete_bank(self, bank_id: UUID, user_id: UUID) -> None:
        """Soft delete an entire bank node.

        Args:
            bank_id (UUID): Pointer to exact resource.
            user_id (UUID): Deletion agent forcing execution.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_manage_bank(user_id=user_id, bank=bank)
        await self.repository.soft_delete_bank(bank, user_id)

    @cache_delete(
        key_builder=lambda self, bank_id, user_id: [
            f"bank:{bank_id}",
            f"banks:user:{user_id}:*",
            f"banks:deleted:user:{user_id}:*",
        ]
    )
    @cache_set(
        key_builder=lambda result: f"bank:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def restore_bank(self, bank_id: UUID, user_id: UUID) -> BankResponse:
        """Restore a softly deleted bank node.

        Args:
            bank_id (UUID): Pointer to exact resource.
            user_id (UUID): Agent forcing execution.

        Returns:
            BankResponse: Exposes public attributes of the restored bank.
        """
        bank = await self.repository.get_deleted_bank_or_raise(bank_id)
        self.validator.check_manage_bank(user_id=user_id, bank=bank)
        restored_bank = await self.repository.restore_bank(bank)
        return BankResponse.model_validate(restored_bank)

    @cache_delete(
        key_builder=lambda self, bank_id, shares, current_user_id: [
            f"bank:{bank_id}",
        ]
    )
    async def share_bank(
        self, bank_id: UUID, shares: List[BankShareItem], current_user_id: UUID
    ) -> None:
        """Grant additional members explicit roles configuring access levels within bank scopes.

        If an owner role is granted, the original owner is downgraded and explicitly logged
        as shifting out of master status.

        Args:
            bank_id (UUID): Focus selection pointer.
            shares (List[BankShareItem]): Role assignment definitions per specific user node.
            current_user_id (UUID): Master controller forcing action.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_manage_bank(user_id=current_user_id, bank=bank)

        for share_item in shares:
            target_user_id = share_item.user_id
            permission = share_item.permission

            if permission == BankPermission.owner:
                await self.repository.update_bank_owner(bank, target_user_id)

                # Check old owner share existence
                old_owner_share = await self.repository.get_share_for_user(
                    bank_id=bank_id, user_id=current_user_id
                )
                if old_owner_share:
                    await self.repository.update_share_permission(
                        old_owner_share, BankPermission.edit
                    )
                else:
                    await self.repository.add_share(
                        bank_id=bank_id,
                        user_id=current_user_id,
                        permission=BankPermission.edit,
                    )

                new_owner_share = await self.repository.get_share_for_user(
                    bank_id=bank_id, user_id=target_user_id
                )
                if new_owner_share:
                    await self.repository.update_share_permission(
                        new_owner_share, BankPermission.owner
                    )
                else:
                    await self.repository.add_share(
                        bank_id=bank_id,
                        user_id=target_user_id,
                        permission=BankPermission.owner,
                    )
            else:
                existing_share = await self.repository.get_share_for_user(
                    bank_id=bank_id, user_id=target_user_id
                )
                if existing_share:
                    await self.repository.update_share_permission(
                        existing_share, permission
                    )
                else:
                    await self.repository.add_share(
                        bank_id=bank_id, user_id=target_user_id, permission=permission
                    )

        await self.repository.batch_flush()

    @cache_delete(
        key_builder=lambda self, bank_id, user_ids, current_user_id: [
            f"bank:{bank_id}",
        ]
    )
    async def unshare_bank(
        self, bank_id: UUID, user_ids: List[UUID], current_user_id: UUID
    ) -> None:
        """Strip read/edit rights from targets against specific bank.

        Cannot delete the ownership role entirely natively.

        Args:
            bank_id (UUID): Scope limitation path string.
            user_ids (List[UUID]): Multiple identifiers selected.
            current_user_id (UUID): Master node executing directive.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_manage_bank(user_id=current_user_id, bank=bank)

        for target_user_id in user_ids:
            if target_user_id == bank.created_by:
                continue

            share = await self.repository.get_share_for_user(
                bank_id=bank_id, user_id=target_user_id
            )
            if share:
                await self.repository.remove_share(share)

        await self.repository.batch_flush()
