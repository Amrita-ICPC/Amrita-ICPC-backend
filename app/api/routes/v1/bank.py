from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AccessControl,
    can_create,
    can_delete,
    can_read,
    can_update,
    check_permission,
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.schema.bank import (
    BankCreate,
    BankDetailResponse,
    BankResponse,
    BankShareRequest,
    BankUnshareRequest,
    BankUpdate,
    BankListResponse
)
from app.schema.contest import MessageResponse
from app.service.bank_service import BankService
from app.service.user_service import UserService

router = APIRouter()


@router.post(
    "/",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new bank",
    dependencies=[can_create("banks")],
)
async def create_bank(
    bank: BankCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Create a new bank.

    Args:
        bank (BankCreate): The bank data to create.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        MessageResponse: A message indicating successful creation.

    Raises:
        BankAlreadyExistsError: If a bank with the same name already exists for the user.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    bank_service = BankService(db)
    created_bank = await bank_service.create_bank(bank, db_user.id)
    logger.info(f"Bank {created_bank.name} with ID {created_bank.id} created by user {db_user.id}")
    
    return MessageResponse(message="Bank created successfully")


@router.get(
    "/",
    response_model=BankListResponse,
    summary="Get all banks",
    dependencies=[can_read("banks")],
)
async def get_all_banks(
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of banks per page"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get all banks accessible to the user.
    
    This includes banks created by the user and banks shared with the user.

    Args:
        page (int): Page number (starts from 1).
        page_size (int): Number of banks per page.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        BankListResponse: A list of banks and the total count.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    skip = (page - 1) * page_size
    bank_service = BankService(db)
    total, banks = await bank_service.get_all_banks(db_user.id, skip, page_size)
    return BankListResponse(total=total, banks=banks)


@router.get(
    "/{bank_id}",
    response_model=BankDetailResponse,
    summary="Get bank details",
    dependencies=[can_read("banks")],
)
async def get_bank(
    bank_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get bank details including questions and shares.
    
    Args:
        bank_id (UUID): The unique identifier of the bank.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        BankDetailResponse: Detailed information about the bank.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankAccessDeniedError: If the user does not have permission to view the bank.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    bank_service = BankService(db)
    return await bank_service.get_bank_by_id(bank_id, db_user.id)


@router.patch(
    "/{bank_id}",
    response_model=MessageResponse,
    summary="Update bank",
    dependencies=[can_update("banks")],
)
async def update_bank(
    bank_id: UUID,
    bank_update: BankUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Update bank details.
    
    Only the owner or users with EDIT permission can update the bank.

    Args:
        bank_id (UUID): The unique identifier of the bank.
        bank_update (BankUpdate): The fields to update.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        MessageResponse: A message indicating successful update.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankPermissionError: If the user has READ-only access.
        BankAccessDeniedError: If the user has no access.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    bank_service = BankService(db)
    await bank_service.update_bank(bank_id, bank_update, db_user.id)
    logger.info(f"Bank with ID {bank_id} updated by user {db_user.id}")

    return MessageResponse(message="Bank updated successfully")


@router.delete(
    "/{bank_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete bank",
    dependencies=[can_delete("banks")],
)
async def delete_bank(
    bank_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Delete a bank.
    
    Only the owner can delete the bank.

    Args:
        bank_id (UUID): The unique identifier of the bank.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        MessageResponse: A message indicating successful deletion.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankPermissionError: If the user is not the owner.
        BankAccessDeniedError: If the user has no access.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    bank_service = BankService(db)
    await bank_service.delete_bank(bank_id, db_user.id)
    logger.info(f"Bank with ID {bank_id} deleted by user {db_user.id}")
    return MessageResponse(message="Bank deleted successfully")


@router.post(
    "/{bank_id}/share",
    response_model=MessageResponse,
    summary="Share bank with users",
    dependencies=[Depends(check_permission("banks", "share"))], 
)
async def share_bank(
    bank_id: UUID,
    share_data: BankShareRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Share bank with other users.
    
    Only the owner can share the bank or transfer ownership.

    Args:
        bank_id (UUID): The unique identifier of the bank.
        share_data (BankShareRequest): The list of users and permissions to share with.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        MessageResponse: A message indicating successful sharing.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankPermissionError: If the user is not the owner.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    bank_service = BankService(db)
    await bank_service.share_bank(
        bank_id, share_data.shares, db_user.id
    )

    logger.info(f"Bank {bank_id} shared by user {db_user.id} to {len(share_data.shares)} recipients")
    return MessageResponse(message="Bank shared successfully")


@router.post(
    "/{bank_id}/unshare",
    response_model=MessageResponse,
    summary="Remove users from bank share",
    dependencies=[Depends(check_permission("banks", "share"))],
)
async def unshare_bank(
    bank_id: UUID,
    unshare_data: BankUnshareRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Remove users from bank share.
    
    Only the owner can remove users.

    Args:
        bank_id (UUID): The unique identifier of the bank.
        unshare_data (BankUnshareRequest): The list of users to remove.
        db (Session): Database session.
        current_user (Dict[str, Any]): The currently authenticated user.

    Returns:
        MessageResponse: A message indicating successful removal.

    Raises:
        BankNotFoundError: If the bank does not exist.
        BankPermissionError: If the user is not the owner.
    """
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    bank_service = BankService(db)
    await bank_service.unshare_bank(
        bank_id, unshare_data.user_ids, db_user.id
    )
    logger.info(f"Bank with ID {bank_id} access removed for users {unshare_data.user_ids} by user {db_user.id}")
    return MessageResponse(message="Users removed from bank share successfully")
