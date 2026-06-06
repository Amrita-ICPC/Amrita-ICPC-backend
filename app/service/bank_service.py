from typing import List
from uuid import UUID

from app.core.cache.decorators import cache_delete, cache_get, cache_set
from app.exceptions.bank import BankOwnerUnshareError
from app.mappers.bank import (
    build_bank_entity,
    build_bank_query_params,
    to_bank_detail_response,
    to_bank_response,
    to_bank_response_list,
)
from app.repositories.bank import BankRepository
from app.schema.bank import (
    BankCreate,
    BankDetailResponse,
    BankResponse,
    BankShareItem,
    BankSharesResponse,
    BankShareUserResponse,
    BankUpdate,
)
from app.schema.user import UserBasicInfo
from app.utils.enums import BankPermission, BankSortBy
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

        bank_entity = build_bank_entity(
            name=bank.name,
            description=bank.description,
            user_id=user_id,
        )
        db_bank = await self.repository.create_bank(bank_entity)

        # Grant ownership instantly via share relationships
        await self.repository.add_share(
            bank_id=db_bank.id, user_id=user_id, permission=BankPermission.owner
        )

        return to_bank_response(db_bank)

    # @cache_get(
    #     key_builder=lambda self, bank_id: f"bank:{bank_id}",
    #     ttl=300,
    # )
    # async def _get_bank_from_cache(self, bank_id: UUID) -> BankDetailResponse:
    #     """Internal helper handling explicit cache access for bank structure.

    #     WARNING: This skips access checks intentionally to load entities uniformly.

    #     Args:
    #         bank_id (UUID): Fetching by database ID.

    #     Returns:
    #         BankDetailResponse: Serialized data representation from DB.
    #     """
    #     bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
    #     return to_bank_detail_response(bank)

    async def get_bank_by_id(self, bank_id: UUID, user_id: UUID) -> BankDetailResponse:
        """Fetch bank details with full relationships and access validation.

        Args:
            bank_id: The bank ID to retrieve.
            user_id: User ID requesting the bank (for permission check).

        Returns:
            BankDetailResponse: Complete bank details with all relationships.

        Raises:
            BankNotFoundError: If bank not found.
            PermissionDeniedError: If user lacks read access.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_read_bank(user_id=user_id, bank=bank)
        return to_bank_detail_response(bank)

    @cache_get(
        key_builder=lambda self, user_id, skip=0, limit=100, search_term=None, sort_by=None: (
            f"banks:user:{user_id}:skip:{skip}:limit:{limit}:search:{search_term or ''}:sort:{sort_by.value if sort_by else ''}"
        ),
        ttl=300,
    )
    async def get_all_banks(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
        search_term: str | None = None,
        sort_by: BankSortBy | None = None,
    ) -> tuple[int, List[BankResponse]]:
        """Fetch paginated list of banks accessible to the user.

        Includes banks created by user and banks shared with user.

        Args:
            user_id: User ID filtering accessible banks.
            skip: Pagination offset.
            limit: Maximum results to return.
            search_term: Search query string.
            sort_by: Optional sort parameter.

        Returns:
            Tuple of (total count, paginated bank responses).
        """
        filters, pagination = build_bank_query_params(
            skip=skip, limit=limit, search_term=search_term, sort_by=sort_by
        )

        result = await self.repository.get_banks_with_filters(
            user_id=user_id, filters=filters, pagination=pagination
        )

        responses = to_bank_response_list(result.items)
        return result.total, responses

    @cache_delete(
        key_builder=lambda self, bank_id, bank_update, user_id: (
            f"banks:user:{user_id}:*"
        ),
    )
    @cache_set(
        key_builder=lambda result: f"bank:{result.id}",
        ttl=300,
        from_result=True,
    )
    async def update_bank(
        self, bank_id: UUID, bank_update: BankUpdate, user_id: UUID
    ) -> BankResponse:
        """Update bank metadata (name, description, etc.).

        Args:
            bank_id: Bank ID to update.
            bank_update: Update payload with desired changes.
            user_id: User ID performing update (must have edit permission).

        Returns:
            BankResponse: Updated bank details.

        Raises:
            BankNotFoundError: If bank not found.
            PermissionDeniedError: If user lacks edit permission.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_edit_bank(user_id=user_id, bank=bank)

        update_data = bank_update.model_dump(exclude_unset=True)
        validated_data = self.validator.construct_valid_update_payload(update_data)

        for field, value in validated_data.items():
            setattr(bank, field, value)

        updated_bank = await self.repository.update_bank(bank)
        return to_bank_response(updated_bank)

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
        key_builder=lambda self, user_id, skip=0, limit=100: (
            f"banks:deleted:user:{user_id}:skip:{skip}:limit:{limit}"
        ),
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
        filters, pagination = build_bank_query_params(skip=skip, limit=limit)

        result = await self.repository.get_soft_deleted_banks(
            user_id=user_id, filters=filters, pagination=pagination
        )

        responses = to_bank_response_list(result.items)
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
        return to_bank_response(restored_bank)

    @cache_delete(
        key_builder=lambda self, bank_id, shares, current_user_id, allow_ownership_transfer=False: [
            f"bank:{bank_id}",
            f"banks:user:{current_user_id}:*",
            # Invalidate cache for all users being shared with
            *[f"banks:user:{s.user_id}:*" for s in shares],
        ]
    )
    async def manage_bank_shares(
        self,
        bank_id: UUID,
        shares: List[BankShareItem],
        current_user_id: UUID,
        allow_ownership_transfer: bool = False,
    ) -> None:
        """Unified share management for add, update, and optional ownership transfer.

        Args:
            bank_id: Bank ID to share.
            shares: List of share items with user IDs and permissions.
            current_user_id: User ID performing the share operation.
            allow_ownership_transfer: Whether to allow ownership transfer (default: False).

        Raises:
            BankNotFoundError: If bank not found.
            PermissionDeniedError: If user lacks manage permission.
        """
        bank = await self.repository.get_bank_or_raise(bank_id, load_relations=True)
        self.validator.check_manage_bank(user_id=current_user_id, bank=bank)

        # Create lookup map for efficient updates
        existing_shares = {s.user_id: s for s in bank.shares}

        for share_item in shares:
            target_user_id = share_item.user_id
            permission = share_item.permission

            # Handle ownership transfer only if explicitly allowed
            if permission == BankPermission.owner:
                if not allow_ownership_transfer:
                    continue

                # Transfer ownership
                await self.repository.update_bank_owner(bank, target_user_id)

                # Downgrade current owner to edit
                if current_user_id in existing_shares:
                    existing_shares[current_user_id].permission = BankPermission.edit
                else:
                    await self.repository.add_share(
                        bank_id, current_user_id, BankPermission.edit
                    )

                # Set new owner
                if target_user_id in existing_shares:
                    existing_shares[target_user_id].permission = BankPermission.owner
                else:
                    await self.repository.add_share(
                        bank_id, target_user_id, BankPermission.owner
                    )
            else:
                # Regular read/edit permission
                if target_user_id in existing_shares:
                    existing_shares[target_user_id].permission = permission
                else:
                    await self.repository.add_share(bank_id, target_user_id, permission)

        await self.repository.batch_flush()

    async def share_bank(
        self,
        bank_id: UUID,
        shares: List[BankShareItem],
        current_user_id: UUID,
    ) -> None:
        """Grant users access to a bank (without ownership transfer).

        Args:
            bank_id: Bank ID to share.
            shares: List of shares to add/update.
            current_user_id: User performing the action.
        """
        await self.manage_bank_shares(
            bank_id=bank_id,
            shares=shares,
            current_user_id=current_user_id,
            allow_ownership_transfer=False,
        )

    @cache_delete(
        key_builder=lambda self, bank_id, target_user_id, current_user_id: [
            f"bank:{bank_id}",
            f"banks:user:{current_user_id}:*",
            f"banks:user:{target_user_id}:*",
        ]
    )
    async def unshare_bank(
        self, bank_id: UUID, target_user_id: UUID, current_user_id: UUID
    ) -> None:
        """Remove a user's access to a bank.

        Args:
            bank_id: Bank ID to unshare.
            target_user_id: User ID to remove access from.
            current_user_id: User performing the action (must have manage permission).

        Raises:
            BankNotFoundError: If bank not found.
            BankOwnerUnshareError: If attempting to unshare the bank owner.
            PermissionDeniedError: If user lacks manage permission.
        """
        bank = await self.repository.get_bank_or_raise(bank_id)
        self.validator.check_manage_bank(user_id=current_user_id, bank=bank)

        # Cannot unshare the bank owner
        if target_user_id == bank.created_by:
            raise BankOwnerUnshareError(str(bank_id), str(target_user_id))

        await self.repository.remove_share(bank_id, target_user_id)

    async def get_bank_shares(
        self,
        bank_id: UUID,
        user_id: UUID,
        email: str | None = None,
        username: str | None = None,
    ) -> BankSharesResponse:
        """Fetch bank shares with optional user filtering.

        Args:
            bank_id: Bank ID to get shares for.
            user_id: User ID requesting shares (must have read access).
            email: Optional email filter for shared users.
            username: Optional username filter for shared users.

        Returns:
            BankSharesResponse: Owner info and list of shared users with permissions.

        Raises:
            BankNotFoundError: If bank not found.
            PermissionDeniedError: If user lacks read access.
        """
        # We use a read check to ensure the user can even see this bank's meta-structure
        bank = await self.repository.get_bank_or_raise(bank_id)
        self.validator.check_read_bank(user_id=user_id, bank=bank)

        owner, shares = await self.repository.get_bank_shares_with_filters(
            bank_id, email, username
        )

        return BankSharesResponse(
            owner=UserBasicInfo.model_validate(owner),
            shares=[
                BankShareUserResponse(
                    **UserBasicInfo.model_validate(share.user).model_dump(),
                    permission=share.permission,
                )
                for share in shares
            ],
        )

    async def update_bank_shares(
        self,
        bank_id: UUID,
        updates: List[BankShareItem],
        current_user_id: UUID,
    ) -> None:
        """Update share permissions for existing shared users (no ownership transfer).

        Args:
            bank_id: Bank ID to update shares for.
            updates: List of share updates (read/edit only, no ownership).
            current_user_id: User ID performing the update.

        Raises:
            BankNotFoundError: If bank not found.
            PermissionDeniedError: If user lacks manage permission.
        """
        bank = await self.repository.get_bank_or_raise(bank_id)

        # Filter out owner and ownership attempts
        filtered_updates = [
            BankShareItem(user_id=u.user_id, permission=u.permission)
            for u in updates
            if u.user_id != bank.created_by and u.permission != BankPermission.owner
        ]

        await self.manage_bank_shares(
            bank_id=bank_id,
            shares=filtered_updates,
            current_user_id=current_user_id,
            allow_ownership_transfer=False,
        )
