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
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.logger import logger
from app.exceptions.auth import PermissionDeniedError
from app.schema.contest import (
    ContestCreate,
    ContestListResponse,
    ContestResponse,
    ContestUpdate,
    MessageResponse,
)
from app.service.contest_service import ContestService
from app.service.user_service import UserService

router = APIRouter()



def get_contest_service(db: Session = Depends(get_db)) -> ContestService:
    return ContestService(db)


@router.post(
    "/",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contest",
    dependencies=[can_create("contests")],
)
async def create_contest(
    contest: ContestCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Create a new contest.

    Only users with admin role can create contests.

    Args:
        contest: Contest creation data
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message

    Raises:
        PermissionDeniedError: If user is not admin
        UserNotFoundError: If user not found in database
    """
    # Fetch the database user using the Keycloak user ID (sub)
    keycloak_user_id = current_user["sub"]
    db_user = UserService.get_user_by_keycloak_id(db, keycloak_user_id)
    created_contest = await service.create_contest(contest, db_user.id)
    logger.info(
        f"Contest '{created_contest.name}' with ID {created_contest.id} created by user {db_user.id}"
    )

    return MessageResponse(message="Contest created successfully")


@router.get(
    "/",
    response_model=ContestListResponse,
    summary="Get all contests",
    dependencies=[can_read("contests")],
)
async def get_all_contests(
    current_user: Dict[str, Any] = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of contests per page"),
    db: Session = Depends(get_db),
    service: ContestService = Depends(get_contest_service),
):
    """
    Get all contests with pagination support.

    Args:
        page: Page number (starts from 1)
        page_size: Number of contests per page (max 100)
        db: Database session
        service: Contest service instance

    Returns:
        List of contests and total count
    """
    kc_id = current_user.get("sub")
    user_id = UserService.get_user_by_keycloak_id(db, kc_id).id
    skip = (page - 1) * page_size
    total, contests = await service.get_all_contests(user_id, skip, page_size)
    return ContestListResponse(total=total, contests=contests)


@router.get(
    "/{contest_id}",
    response_model=ContestResponse,
    summary="Get contest by ID",
    dependencies=[can_read("contests")],
)
async def get_contest(
    contest_id: UUID,
    service: ContestService = Depends(get_contest_service),
):
    """
    Get a specific contest by its ID.

    Args:
        contest_id: Contest ID
        service: Contest service instance

    Returns:
        Contest details

    Raises:
        ContestNotFoundError: If contest with given ID not found
    """
    return await service.get_contest_by_id(contest_id)


@router.patch(
    "/{contest_id}",
    response_model=MessageResponse,
    summary="Update contest",
    dependencies=[can_update("contests")],
)
async def update_contest(
    contest_id: UUID,
    contest_data: ContestUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Partially update an existing contest with provided fields.

    Only users with admin role can update contests.
    Only the fields provided in the request body will be updated. Other fields remain unchanged.

    Args:
        contest_id: Contest ID
        contest_data: Contest update data (partial update - only provided fields are updated)
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message

    Raises:
        ContestNotFoundError: If contest with given ID not found
        PermissionDeniedError: If user is not admin
    """
    kc_id = current_user.get("sub")
    user_id = UserService.get_user_by_keycloak_id(db, kc_id).id
    await service.update_contest(contest_id, contest_data, user_id)
    logger.info(f"Contest with ID {contest_id} updated by user {user_id}")

    return MessageResponse(message="Contest updated successfully")


@router.delete(
    "/{contest_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete contest",
    dependencies=[can_delete("contests")],
)
async def delete_contest(
    contest_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Delete a contest by its ID.

    Only users with admin role can delete contests.

    Args:
        contest_id: Contest ID
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message

    Raises:
        ContestNotFoundError: If contest with given ID not found
        PermissionDeniedError: If user is not admin
    """
    kc_id = current_user.get("sub")
    user_id = UserService.get_user_by_keycloak_id(db, kc_id).id
    await service.delete_contest(contest_id, user_id)
    logger.info(f"Contest with ID {contest_id} deleted by user {user_id}")

    return MessageResponse(message="Contest deleted successfully")
