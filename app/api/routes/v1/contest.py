from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    can_create,
    can_delete,
    can_read,
    can_update,
    get_current_user,
)
from app.core.clients.database import get_db
from app.core.logger import logger
from app.schema.contest import (
    ContestCreate,
    ContestListResponse,
    ContestResponse,
    ContestUpdate,
    InstructorListResponse,
    InstructorManageRequest,
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
    db_user = await UserService.get_user_by_keycloak_id(db, keycloak_user_id)
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
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    skip = (page - 1) * page_size
    total, contests = await service.get_all_contests(user_id, skip, page_size)
    return ContestListResponse(total=total, contests=contests)


@router.get(
    "/deleted",
    response_model=ContestListResponse,
    summary="Get soft-deleted contests",
    dependencies=[can_read("contests")],
)
async def get_deleted_contests(
    current_user: Dict[str, Any] = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of contests per page"),
    db: Session = Depends(get_db),
    service: ContestService = Depends(get_contest_service),
):
    """
    Get all soft-deleted contests with pagination support.

    Args:
        page: Page number (starts from 1)
        page_size: Number of contests per page (max 100)
        db: Database session
        service: Contest service instance

    Returns:
        List of soft-deleted contests and total count
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    skip = (page - 1) * page_size
    total, contests = await service.get_soft_deleted_contests(user_id, skip, page_size)
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
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific contest by its ID.

    Args:
        contest_id: Contest ID
        service: Contest service instance
        current_user: Current authenticated user
        db: Database session
    Returns:
        Contest details

    Raises:
        ContestNotFoundError: If contest with given ID not found
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    return await service.get_contest_by_id(contest_id, user_id)


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
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.update_contest(contest_id, contest_data, user_id)
    logger.info(f"Contest with ID {contest_id} updated by user {user_id}")

    return MessageResponse(message="Contest updated successfully")


@router.post(
    "/{contest_id}/publish",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish contest",
    dependencies=[can_update("contests")],
)
async def publish_contest(
    contest_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Publish a contest.

    Only users with admin role can publish contests.
    Publishing a contest sets the published_at timestamp and updates the status.

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
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.publish_contest(contest_id, user_id)
    logger.info(f"Contest with ID {contest_id} published by user {user_id}")

    return MessageResponse(message="Contest published successfully")


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
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.delete_contest(contest_id, user_id)
    logger.info(f"Contest with ID {contest_id} deleted by user {user_id}")

    return MessageResponse(message="Contest deleted successfully")


@router.delete(
    "/{contest_id}/soft-delete",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft delete contest",
    dependencies=[can_delete("contests")],
)
async def soft_delete_contest(
    contest_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Soft delete a contest.

    Args:
        contest_id: Contest ID
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.soft_delete_contest(contest_id, user_id)
    logger.info(f"Contest {contest_id} soft deleted by user {user_id}")

    return MessageResponse(message="Contest soft deleted successfully")


@router.post(
    "/{contest_id}/restore",
    response_model=ContestResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore soft-deleted contest",
    dependencies=[can_update("contests")],
)
async def restore_contest(
    contest_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Restore a soft-deleted contest.

    Args:
        contest_id: Contest ID
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Restored contest object
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    contest = await service.restore_contest(contest_id, user_id)
    logger.info(f"Contest {contest_id} restored by user {user_id}")
    return contest


@router.post(
    "/{contest_id}/instructors",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign instructors to contest",
    dependencies=[can_update("contests")],
)
async def assign_instructors_to_contest(
    contest_id: UUID,
    request: InstructorManageRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Assign a list of instructors to a contest.

    Only users with admin role can assign instructors to contests.

    Args:
        contest_id: Contest ID
        request: Request containing list of instructor IDs
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message

    Raises:
        ContestNotFoundError: If contest not found
        UserNotFoundError: If any instructor not found
        InstructorAlreadyAssignedError: If any instructor is already assigned
        PermissionDeniedError: If user doesn't have permission
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.assign_instructors_to_contest(contest_id, request, user_id)
    logger.info(
        f"Assigned {len(request.instructor_ids)} instructors to contest {contest_id} by user {user_id}"
    )

    return MessageResponse(message="Instructors assigned successfully")


@router.delete(
    "/{contest_id}/instructors",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove instructors from contest",
    dependencies=[can_update("contests")],
)
async def remove_instructors_from_contest(
    contest_id: UUID,
    request: InstructorManageRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ContestService = Depends(get_contest_service),
):
    """
    Remove a list of instructors from a contest.

    Only users with admin role can remove instructors from contests.

    Args:
        contest_id: Contest ID
        request: Request containing list of instructor IDs
        db: Database session
        current_user: Current authenticated user
        service: Contest service instance

    Returns:
        Success message

    Raises:
        ContestNotFoundError: If contest not found
        InstructorNotAssignedError: If any instructor is not assigned to the contest
        PermissionDeniedError: If user doesn't have permission
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(db, kc_id)).id
    await service.remove_instructors_from_contest(contest_id, request, user_id)
    logger.info(
        f"Removed {len(request.instructor_ids)} instructors from contest {contest_id} by user {user_id}"
    )

    return MessageResponse(message="Instructors removed successfully")


@router.get(
    "/{contest_id}/instructors",
    response_model=InstructorListResponse,
    summary="Get contest instructors",
    dependencies=[can_read("contests")],
)
async def get_contest_instructors(
    contest_id: UUID,
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(
        10, ge=1, le=100, description="Number of instructors per page"
    ),
    service: ContestService = Depends(get_contest_service),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get all instructors assigned to a contest with pagination support.

    Only users who can manage the contest (creators or assigned instructors) can view the instructors list.

    Args:
        contest_id: Contest ID
        page: Page number (starts from 1)
        page_size: Number of instructors per page (max 100)
        service: Contest service instance
        current_user: Current authenticated user

    Returns:
        List of instructors assigned to the contest

    Raises:
        ContestNotFoundError: If contest not found
        PermissionDeniedError: If user cannot manage the contest
    """
    kc_id = current_user.get("sub")
    user_id = (await UserService.get_user_by_keycloak_id(service.db, kc_id)).id
    skip = (page - 1) * page_size
    result = await service.get_contest_instructors(contest_id, user_id, skip, page_size)
    logger.info(
        f"Retrieved {len(result.instructors)} instructors for contest {contest_id}"
    )

    return result

    return MessageResponse(message="Instructors removed successfully")
