from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    check_permission,
    get_current_user_id,
)
from app.core.clients.database import get_db
from app.core.logger import logger
from app.core.response import create_api_response
from app.repositories.bank import BankRepository
from app.schema.bank import (
    BankCreate,
    BankDetailResponse,
    BankResponse,
    BankShareRequest,
    BankUnshareRequest,
    BankUpdate,
)
from app.schema.base import APIResponse
from app.service.bank_service import BankService
from app.utils.pagination import get_pagination
from app.validators.bank import BankValidator

router = APIRouter()


def get_bank_service(db: AsyncSession = Depends(get_db)) -> BankService:
    """Dependency injector linking repository, validator into the service.

    Args:
        db (AsyncSession): Database session passed from FastAPI dependencies.

    Returns:
        BankService: Fully configured service class instance.
    """
    repository = BankRepository(db)
    validator = BankValidator()
    return BankService(repository, validator)


@router.post(
    "/",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bank",
    dependencies=[can_create("banks")],
)
async def create_bank(
    request: Request,
    bank: BankCreate,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Create a new bank.

    Args:
        request (Request): Framework context.
        bank (BankCreate): The bank data to create.
        user_id (UUID): The currently authenticated user ID via Keycloak.
        service (BankService): Injected domain service handling bank.

    Returns:
        APIResponse: Standardized response encapsulating creation metadata.
    """
    created_bank = await service.create_bank(bank, user_id)
    logger.info(
        f"Bank '{created_bank.name}' with ID {created_bank.id} created by user {user_id}"
    )

    return create_api_response(
        request,
        data=created_bank,
        message="Bank created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/",
    response_model=APIResponse[list[BankResponse]],
    summary="Get all banks",
    dependencies=[can_read("banks")],
)
async def get_all_banks(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of banks per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Get all banks accessible to the user.

    This includes banks created by the user and banks shared with the user.

    Args:
        request (Request): Framework context.
        page (int): Page number (starts from 1).
        page_size (int): Number of banks per page.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the list of banks and pagination state.
    """
    skip = (page - 1) * page_size
    total, banks = await service.get_all_banks(user_id, skip, page_size)

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=banks,
        message="Banks fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/deleted",
    response_model=APIResponse[list[BankResponse]],
    summary="Get softly deleted banks",
    dependencies=[can_read("banks")],
)
async def get_deleted_banks(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of banks per page"),
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Get all softly deleted banks accessible to the user.

    Args:
        request (Request): Framework context.
        page (int): Page number (starts from 1).
        page_size (int): Number of banks per page.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Standardized response encapsulating the list of softly deleted banks.
    """
    skip = (page - 1) * page_size
    total, banks = await service.get_soft_deleted_banks(user_id, skip, page_size)

    pagination = get_pagination(total=total, page=page, page_size=page_size)

    return create_api_response(
        request,
        data=banks,
        message="Deleted banks fetched successfully",
        pagination=pagination,
    )


@router.get(
    "/{bank_id}",
    response_model=APIResponse[BankDetailResponse],
    summary="Get bank details",
    dependencies=[can_read("banks")],
)
async def get_bank(
    request: Request,
    bank_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Get bank details including questions and shares.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Detailed information block for the bank.
    """
    bank_details = await service.get_bank_by_id(bank_id, user_id)

    return create_api_response(
        request, data=bank_details, message="Bank details fetched successfully"
    )


@router.patch(
    "/{bank_id}",
    response_model=APIResponse,
    summary="Update bank",
    dependencies=[can_update("banks")],
)
async def update_bank(
    request: Request,
    bank_id: UUID,
    bank_update: BankUpdate,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Update bank details.

    Only the owner or users with EDIT permission can update the bank.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        bank_update (BankUpdate): The fields to update.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Confirmation flag on update.
    """
    await service.update_bank(bank_id, bank_update, user_id)
    logger.info(f"Bank with ID {bank_id} updated by user {user_id}")

    return create_api_response(request, data=None, message="Bank updated successfully")


@router.delete(
    "/{bank_id}",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete bank",
    dependencies=[can_delete("banks")],
)
async def delete_bank(
    request: Request,
    bank_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Delete a bank.

    Only the owner can delete the bank.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.
    """
    await service.delete_bank(bank_id, user_id)
    logger.info(f"Bank with ID {bank_id} deleted by user {user_id}")
    return create_api_response(request, data=None, message="Bank deleted successfully")


@router.delete(
    "/{bank_id}/soft-delete",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft delete bank",
    dependencies=[can_delete("banks")],
)
async def soft_delete_bank(
    request: Request,
    bank_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Soft delete a bank without physically removing it.

    Only the owner or authorized roles can manage this deletion status.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Success confirmation.
    """
    await service.soft_delete_bank(bank_id, user_id)
    logger.info(f"Bank {bank_id} soft deleted by user {user_id}")
    return create_api_response(
        request, data=None, message="Bank soft deleted successfully"
    )


@router.post(
    "/{bank_id}/restore",
    response_model=APIResponse[BankResponse],
    status_code=status.HTTP_200_OK,
    summary="Restore softly deleted bank",
    dependencies=[can_update("banks")],
)
async def restore_bank(
    request: Request,
    bank_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Restore a softly deleted bank.

    Returns the bank to an active status.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: The restored bank object block.
    """
    bank = await service.restore_bank(bank_id, user_id)
    logger.info(f"Bank {bank_id} restored by user {user_id}")
    return create_api_response(request, data=bank, message="Bank restored successfully")


@router.post(
    "/{bank_id}/share",
    response_model=APIResponse,
    summary="Share bank with users",
    dependencies=[Depends(check_permission("banks", "share"))],
)
async def share_bank(
    request: Request,
    bank_id: UUID,
    share_data: BankShareRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Share bank with other users.

    Only the owner can share the bank or transfer ownership.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        share_data (BankShareRequest): The list of users and permissions to share with.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Success confirmation on sharing execution.
    """
    await service.share_bank(bank_id, share_data.shares, user_id)

    logger.info(
        f"Bank {bank_id} shared by user {user_id} to {len(share_data.shares)} recipients"
    )
    return create_api_response(request, data=None, message="Bank shared successfully")


@router.post(
    "/{bank_id}/unshare",
    response_model=APIResponse,
    summary="Remove users from bank share",
    dependencies=[Depends(check_permission("banks", "share"))],
)
async def unshare_bank(
    request: Request,
    bank_id: UUID,
    unshare_data: BankUnshareRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: BankService = Depends(get_bank_service),
):
    """
    Remove users from bank share.

    Only the owner can remove users.

    Args:
        request (Request): Framework context.
        bank_id (UUID): The unique identifier of the bank.
        unshare_data (BankUnshareRequest): The list of users to remove.
        user_id (UUID): Authenticated user ID.
        service (BankService): Injected domain service.

    Returns:
        APIResponse: Explicit success confirmation.
    """
    await service.unshare_bank(bank_id, unshare_data.user_ids, user_id)

    logger.info(
        f"Bank with ID {bank_id} access removed for {len(unshare_data.user_ids)} users by user {user_id}"
    )
    return create_api_response(
        request, data=None, message="Users removed from bank share successfully"
    )
